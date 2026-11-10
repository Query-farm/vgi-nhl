"""Tests for the NHL HTTP boundary: retries, redirects, caching, and errors."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from vgi_nhl import api


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api.time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def _base_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NHL_WEB_BASE_URL", "https://web.test/v1/")
    monkeypatch.setenv("NHL_STATS_BASE_URL", "https://stats.test/stats/rest/en")
    monkeypatch.setenv("NHL_SEARCH_BASE_URL", "https://search.test/api/v1")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_default_base_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NHL_WEB_BASE_URL", "NHL_STATS_BASE_URL", "NHL_SEARCH_BASE_URL"):
        monkeypatch.delenv(name)
    assert api.web_base_url() == "https://api-web.nhle.com/v1"
    assert api.stats_base_url() == "https://api.nhle.com/stats/rest/en"
    assert api.search_base_url() == "https://search.d3.nhle.com/api/v1"


def test_sends_honest_user_agent_and_reads_max_age() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://web.test/v1/standings/2024-04-18"
        assert request.headers["user-agent"] == api.USER_AGENT
        assert api.USER_AGENT.startswith("vgi-nhl/")
        assert "+https://github.com/Query-farm/vgi-nhl" in api.USER_AGENT
        return httpx.Response(200, json={"standings": []}, headers={"Cache-Control": "max-age=14"})

    with _client(handler) as client:
        response = api.web("standings/2024-04-18", client=client)
    assert response.payload == {"standings": []}
    assert response.ttl == 14


def test_follows_now_redirects_and_reports_final_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/standings/now":
            return httpx.Response(307, headers={"Location": "https://web.test/v1/standings/2026-11-10"})
        return httpx.Response(200, json={"standings": [{"seasonId": 20262027}]})

    with _client(handler) as client:
        response = api.web("standings/now", client=client)
    assert response.url == "https://web.test/v1/standings/2026-11-10"
    assert response.payload["standings"][0]["seasonId"] == 20262027
    assert response.ttl == api.DEFAULT_CACHE_TTL


def test_retries_429_then_succeeds() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        assert api.web("x", client=client).payload == {"ok": True}
    assert len(calls) == 3


def test_gives_up_after_max_attempts() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(502, text="bad gateway")

    with _client(handler) as client, pytest.raises(api.NhlApiError, match="HTTP 502"):
        api.web("x", client=client)
    assert len(calls) == api.MAX_ATTEMPTS


def test_retries_transport_errors() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=[])

    with _client(handler) as client:
        assert api.search("search/player", {"q": "x"}, client=client).payload == []


def test_transport_errors_eventually_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with _client(handler) as client, pytest.raises(httpx.ConnectError):
        api.web("x", client=client)


def test_not_found_is_a_distinct_error() -> None:
    with (
        _client(lambda request: httpx.Response(404, text="Not Found")) as client,
        pytest.raises(api.NhlNotFoundError, match="HTTP 404"),
    ):
        api.web("player/1/landing", client=client)


def test_client_error_is_descriptive() -> None:
    with (
        _client(lambda request: httpx.Response(400, text="bad cayenne")) as client,
        pytest.raises(api.NhlApiError, match="HTTP 400.*bad cayenne"),
    ):
        api.stats("skater/summary", client=client)


def test_non_json_body_is_rejected() -> None:
    with (
        _client(lambda request: httpx.Response(200, text="<html>")) as client,
        pytest.raises(ValueError, match="non-JSON"),
    ):
        api.web("x", client=client)


def test_responses_are_cached_for_their_lifetime() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"n": len(calls)}, headers={"Cache-Control": "max-age=60"})

    with _client(handler) as client:
        first = api.web("x", {"a": 1}, client=client)
        second = api.web("x", {"a": 1}, client=client)
        other = api.web("x", {"a": 2}, client=client)
    assert first.payload == second.payload == {"n": 1}
    assert other.payload == {"n": 2}
    assert 0 < second.ttl <= 60
    assert len(calls) == 2


def test_no_store_and_zero_max_age_are_not_cached() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        header = "no-store" if request.url.path.endswith("a") else "max-age=0"
        return httpx.Response(200, json={}, headers={"Cache-Control": header})

    with _client(handler) as client:
        for path in ("a", "a", "b", "b"):
            assert api.web(path, client=client).ttl == 0
    assert len(calls) == 4


def test_cache_expires_and_evicts(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = api._ResponseCache(max_entries=2)
    now = [1_000.0]
    monkeypatch.setattr(api.time, "monotonic", lambda: now[0])
    cache.store("a", api.ApiResponse(payload=1, url="a", ttl=10))
    cache.store("b", api.ApiResponse(payload=2, url="b", ttl=10))
    cache.store("c", api.ApiResponse(payload=3, url="c", ttl=10))
    assert cache.lookup("a") is None
    assert cache.lookup("b").payload == 2
    now[0] += 11
    assert cache.lookup("b") is None


def test_max_age_is_capped() -> None:
    response = httpx.Response(200, headers={"Cache-Control": "public, max-age=999999"})
    assert api._ttl(response) == api.MAX_CACHE_TTL


def test_retry_delay_honours_retry_after_forms() -> None:
    assert api._retry_delay(httpx.Response(429, headers={"Retry-After": "3"}), 0) == 3
    assert api._retry_delay(httpx.Response(429, headers={"Retry-After": "999"}), 0) == api.MAX_RETRY_DELAY
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=5), usegmt=True)
    assert 0 < api._retry_delay(httpx.Response(429, headers={"Retry-After": future}), 0) <= 5
    assert 0 < api._retry_delay(httpx.Response(429, headers={"Retry-After": "soon"}), 1) <= 0.625
    assert 0 < api._retry_delay(None, 0) <= 0.3125


def test_deadline_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "QUERY_TIMEOUT", -1.0)
    with (
        _client(lambda request: httpx.Response(200, json={})) as client,
        pytest.raises(TimeoutError, match="exceeded"),
    ):
        api.web("x", client=client)


def test_stats_report_requests_every_row_with_a_stable_sort() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert request.url.path == "/stats/rest/en/skater/summary"
        assert params["limit"] == "-1"
        assert params["cayenneExp"] == "seasonId=20252026 and gameTypeId=3"
        assert json.loads(params["sort"]) == [
            {"property": "points", "direction": "DESC"},
            {"property": "playerId", "direction": "ASC"},
        ]
        return httpx.Response(200, json={"data": [{"playerId": 1}], "total": 1})

    with _client(handler) as client:
        response = api.stats_report(
            "skater/summary",
            season=20252026,
            game_type=3,
            sort=[("points", "DESC"), ("playerId", "ASC")],
            client=client,
        )
    assert response.payload["data"] == [{"playerId": 1}]


def test_stats_report_rejects_malformed_payload() -> None:
    with (
        _client(lambda request: httpx.Response(200, json={"data": {}})) as client,
        pytest.raises(ValueError, match="not an array"),
    ):
        api.stats_report("goalie/summary", season=20252026, game_type=2, sort=[], client=client)


def test_require_dict_checks_shape() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        api.require_dict(api.ApiResponse(payload=[], url="u", ttl=0))
    with pytest.raises(ValueError, match="no 'plays' field"):
        api.require_dict(api.ApiResponse(payload={}, url="u", ttl=0), "plays")


def test_season_for_picks_latest_started_season() -> None:
    seasons = [
        {"id": 20242025, "standingsStart": "2024-10-04"},
        {"id": 20252026, "standingsStart": "2025-10-07"},
        {"id": 20262027, "standingsStart": "2026-09-29"},
    ]
    assert api.season_for(date(2026, 11, 10), seasons) == 20262027
    assert api.season_for(date(2026, 7, 1), seasons) == 20252026
    with pytest.raises(ValueError, match="no season"):
        api.season_for(date(2000, 1, 1), seasons)


def test_current_season_reads_standings_season() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/standings-season"
        return httpx.Response(200, json={"seasons": [{"id": 19171918, "standingsStart": "1917-12-19"}]})

    with _client(handler) as client:
        assert api.current_season(client=client) == 19171918


def test_owned_client_is_used_without_an_injected_one(replay: str) -> None:
    assert api.web("standings-season").payload["seasons"]
