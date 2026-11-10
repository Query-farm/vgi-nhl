"""Small, read-only client for the NHL's public web and stats APIs.

Three keyless hosts back the catalog:

* ``api-web.nhle.com/v1`` - the NHL.com and app backend: standings, schedules,
  scores, rosters, player pages, game logs, box scores, play-by-play, leaders,
  the playoff bracket, and draft picks.
* ``api.nhle.com/stats/rest/en`` - the NHL.com/stats reporting service: season
  skater, goalie, and team reports, franchises, teams, and shift charts.
* ``search.d3.nhle.com`` - the NHL.com player search index.

Every outbound request goes through :func:`_request`, which retries 429 and
transient 5xx responses with ``Retry-After``-aware backoff, follows the NHL's
``now``/``current`` 307 redirects, bounds concurrency, and enforces a total
deadline. Successful JSON responses are kept in a small in-process cache for
the origin's ``max-age`` (or a conservative default when the origin sends
none) so repeated scans in one session do not re-hit the NHL.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from vgi_nhl import __version__

DEFAULT_WEB_BASE_URL = "https://api-web.nhle.com/v1"
DEFAULT_STATS_BASE_URL = "https://api.nhle.com/stats/rest/en"
DEFAULT_SEARCH_BASE_URL = "https://search.d3.nhle.com/api/v1"
USER_AGENT = f"vgi-nhl/{__version__} (+https://github.com/Query-farm/vgi-nhl)"

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
MAX_RETRY_DELAY = 30.0
QUERY_TIMEOUT = 120.0
MAX_CONCURRENT_REQUESTS = 4
# The NHL publishes no rate limit and the stats service sends no Cache-Control.
# Without an origin policy, identical requests are reused for one minute.
DEFAULT_CACHE_TTL = 60
MAX_CACHE_TTL = 3_600
MAX_CACHE_ENTRIES = 256

logger = logging.getLogger(__name__)
_request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

_MAX_AGE = re.compile(r"(?:^|[,\s])max-age=(\d+)", re.IGNORECASE)
_NO_STORE = re.compile(r"(?:^|[,\s])no-store(?:$|[,\s])", re.IGNORECASE)


class NhlApiError(RuntimeError):
    """A failed response from one of the NHL APIs."""

    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"NHL API returned HTTP {status} for {url}: {body[:400]}")
        self.status = status


class NhlNotFoundError(NhlApiError):
    """The NHL has no resource at the requested path (unknown game, player, team, or season)."""


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """A decoded JSON payload plus the final URL and the freshness to advertise."""

    payload: Any
    url: str
    ttl: int


def web_base_url() -> str:
    """Return the api-web root, optionally overridden for hermetic tests."""
    return os.environ.get("NHL_WEB_BASE_URL", DEFAULT_WEB_BASE_URL).rstrip("/")


def stats_base_url() -> str:
    """Return the stats REST root, optionally overridden for hermetic tests."""
    return os.environ.get("NHL_STATS_BASE_URL", DEFAULT_STATS_BASE_URL).rstrip("/")


def search_base_url() -> str:
    """Return the player-search root, optionally overridden for hermetic tests."""
    return os.environ.get("NHL_SEARCH_BASE_URL", DEFAULT_SEARCH_BASE_URL).rstrip("/")


class _ResponseCache:
    """A thread-safe LRU of decoded responses with per-entry expiry."""

    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, ApiResponse]] = OrderedDict()
        self._lock = threading.Lock()

    def lookup(self, key: str) -> ApiResponse | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, response = entry
            if expires_at <= time.monotonic():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            remaining = max(1, round(expires_at - time.monotonic()))
            return ApiResponse(payload=response.payload, url=response.url, ttl=remaining)

    def store(self, key: str, response: ApiResponse) -> None:
        if response.ttl <= 0:
            return
        with self._lock:
            self._entries[key] = (time.monotonic() + response.ttl, response)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_cache = _ResponseCache(MAX_CACHE_ENTRIES)


def clear_cache() -> None:
    """Drop every cached response (used by tests and long-lived embedders)."""
    _cache.clear()


def _ttl(response: httpx.Response) -> int:
    """Return the freshness lifetime the origin allows, or the default when it is silent."""
    cache_control = response.headers.get("cache-control", "")
    if _NO_STORE.search(cache_control):
        return 0
    match = _MAX_AGE.search(cache_control)
    if match is None:
        return DEFAULT_CACHE_TTL
    return min(int(match.group(1)), MAX_CACHE_TTL)


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Return a bounded Retry-After delay or exponential backoff with jitter."""
    if response is not None:
        raw = response.headers.get("retry-after")
        if raw:
            try:
                delay = float(raw)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(raw)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    delay = (retry_at - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = -1.0
            if delay >= 0:
                return min(delay, MAX_RETRY_DELAY)
    base = min(0.25 * 2**attempt, MAX_RETRY_DELAY)
    return min(base + random.uniform(0, base * 0.25), MAX_RETRY_DELAY)


def _timeout_error() -> TimeoutError:
    return TimeoutError(f"NHL API query exceeded {QUERY_TIMEOUT:g} seconds")


def _request(
    url: str,
    params: Mapping[str, str | int],
    *,
    client: httpx.Client,
    deadline: float,
) -> httpx.Response:
    """Issue the connector's only kind of outbound request, retrying transient failures."""
    for attempt in range(MAX_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _timeout_error()
        started = time.monotonic()
        try:
            if not _request_slots.acquire(timeout=remaining):
                raise _timeout_error()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _timeout_error()
                response = client.get(
                    url,
                    params=params,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                    follow_redirects=True,
                    timeout=httpx.Timeout(min(30.0, remaining), connect=min(10.0, remaining)),
                )
            finally:
                _request_slots.release()
        except httpx.TransportError:
            logger.warning(
                "nhl_api_transport_error url=%s attempt=%d duration_ms=%d",
                url,
                attempt + 1,
                round((time.monotonic() - started) * 1_000),
            )
            if attempt + 1 == MAX_ATTEMPTS:
                raise
            time.sleep(min(_retry_delay(None, attempt), max(0.0, deadline - time.monotonic())))
            continue
        logger.debug(
            "nhl_api_response url=%s status=%d attempt=%d duration_ms=%d",
            url,
            response.status_code,
            attempt + 1,
            round((time.monotonic() - started) * 1_000),
        )
        if response.status_code not in RETRYABLE_STATUSES or attempt + 1 == MAX_ATTEMPTS:
            return response
        delay = min(_retry_delay(response, attempt), max(0.0, deadline - time.monotonic()))
        logger.warning(
            "nhl_api_retry url=%s status=%d attempt=%d delay_seconds=%.3f",
            url,
            response.status_code,
            attempt + 1,
            delay,
        )
        time.sleep(delay)
    raise AssertionError("retry loop exited without a response")


def get_json(
    base: str,
    path: str,
    params: Mapping[str, str | int] | None = None,
    *,
    client: httpx.Client | None = None,
) -> ApiResponse:
    """GET one JSON document, consulting and filling the in-process cache."""
    url = f"{base}/{path.lstrip('/')}"
    query = dict(params or {})
    key = url + "?" + json.dumps(sorted(query.items()), default=str)
    cached = _cache.lookup(key)
    if cached is not None:
        return cached

    deadline = time.monotonic() + QUERY_TIMEOUT
    if client is not None:
        response = _request(url, query, client=client, deadline=deadline)
    else:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as owned:
            response = _request(url, query, client=owned, deadline=deadline)
    if response.status_code == 404:
        raise NhlNotFoundError(response.status_code, url, response.text)
    if not response.is_success:
        raise NhlApiError(response.status_code, url, response.text)
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError(f"NHL API returned a non-JSON body for {url}") from error
    result = ApiResponse(payload=payload, url=str(response.url), ttl=_ttl(response))
    _cache.store(key, result)
    return result


def web(path: str, params: Mapping[str, str | int] | None = None, **kwargs: Any) -> ApiResponse:
    """GET a path below the api-web root."""
    return get_json(web_base_url(), path, params, **kwargs)


def stats(path: str, params: Mapping[str, str | int] | None = None, **kwargs: Any) -> ApiResponse:
    """GET a path below the stats REST root."""
    return get_json(stats_base_url(), path, params, **kwargs)


def search(path: str, params: Mapping[str, str | int] | None = None, **kwargs: Any) -> ApiResponse:
    """GET a path below the player-search root."""
    return get_json(search_base_url(), path, params, **kwargs)


def require_dict(response: ApiResponse, key: str | None = None) -> dict[str, Any]:
    """Return the payload object, verifying an expected top-level key when given."""
    payload = response.payload
    if not isinstance(payload, dict):
        raise ValueError(f"NHL API response for {response.url} is not a JSON object")
    if key is not None and key not in payload:
        raise ValueError(f"NHL API response for {response.url} has no {key!r} field")
    return payload


def require_list(value: Any, what: str) -> list[dict[str, Any]]:
    """Return the dict items of a JSON array, rejecting a non-array value."""
    if not isinstance(value, list):
        raise ValueError(f"NHL API {what} is not an array")
    return [item for item in value if isinstance(item, dict)]


def stats_report(
    report: str,
    *,
    season: int,
    game_type: int,
    sort: list[tuple[str, str]],
    client: httpx.Client | None = None,
) -> ApiResponse:
    """Fetch a complete stats REST report (``limit=-1``) for one season and game type."""
    params: dict[str, str | int] = {
        "limit": -1,
        "start": 0,
        "sort": json.dumps(
            [{"property": name, "direction": direction} for name, direction in sort],
            separators=(",", ":"),
        ),
        "cayenneExp": f"seasonId={season} and gameTypeId={game_type}",
    }
    response = stats(report, params, client=client)
    require_list(require_dict(response, "data")["data"], f"{report} data")
    return response


def season_for(day: date, seasons: list[dict[str, Any]]) -> int:
    """Return the latest season whose standings window has started on ``day``."""
    started = [
        value["id"]
        for value in seasons
        if isinstance(value.get("id"), int)
        and isinstance(value.get("standingsStart"), str)
        and value["standingsStart"] <= day.isoformat()
    ]
    if not started:
        raise ValueError("NHL season list has no season starting on or before the requested date")
    return max(started)


def current_season(*, client: httpx.Client | None = None) -> int:
    """Resolve the NHL's current (or most recent) season id, such as 20262027."""
    response = web("standings-season", client=client)
    seasons = require_list(require_dict(response, "seasons")["seasons"], "standings-season seasons")
    return season_for(datetime.now(UTC).date(), seasons)
