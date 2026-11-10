"""Shared fixtures: recorded NHL responses and a local server that replays them."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from vgi_nhl import api

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Routes the replay server answers. A string value names a fixture; a tuple is a
# 307 redirect, mirroring the NHL's own ``now``/``current`` aliases.
ROUTES: dict[str, str | tuple[str, str]] = {
    "/v1/standings/now": ("redirect", "/v1/standings/2024-04-18"),
    "/v1/standings/2024-04-18": "standings_2024-04-18.json",
    "/v1/standings-season": "standings_season.json",
    "/v1/schedule/now": ("redirect", "/v1/schedule/2025-10-07"),
    "/v1/schedule/2025-10-07": "schedule_2025-10-07.json",
    "/v1/score/now": ("redirect", "/v1/score/2025-10-07"),
    "/v1/score/2025-10-07": "score_2025-10-07.json",
    "/v1/club-schedule-season/TOR/now": ("redirect", "/v1/club-schedule-season/TOR/20252026"),
    "/v1/club-schedule-season/TOR/20252026": "club_schedule_TOR_20252026.json",
    "/v1/playoff-bracket/2025": "playoff_bracket_2025.json",
    "/v1/draft/picks/2025/all": "draft_picks_2025.json",
    "/v1/skater-stats-leaders/current": ("redirect", "/v1/skater-stats-leaders/20252026/2"),
    "/v1/skater-stats-leaders/20252026/2": "skater_leaders_20252026_2.json",
    "/v1/goalie-stats-leaders/current": ("redirect", "/v1/goalie-stats-leaders/20252026/2"),
    "/v1/goalie-stats-leaders/20252026/2": "goalie_leaders_20252026_2.json",
    "/v1/roster/TOR/current": ("redirect", "/v1/roster/TOR/20252026"),
    "/v1/roster/TOR/20252026": "roster_TOR_20252026.json",
    "/v1/player/8478402/landing": "player_8478402_landing.json",
    "/v1/player/8475683/landing": "player_8475683_landing.json",
    "/v1/player/8478402/game-log/20252026/2": "game_log_8478402_20252026_2.json",
    "/v1/player/8475683/game-log/20252026/2": "game_log_8475683_20252026_2.json",
    "/v1/gamecenter/2025020001/boxscore": "boxscore_2025020001.json",
    "/v1/gamecenter/2025020001/play-by-play": "play_by_play_2025020001.json",
    "/stats/rest/en/skater/summary": "skater_summary_20252026_2.json",
    "/stats/rest/en/skater/realtime": "skater_realtime_20252026_2.json",
    "/stats/rest/en/goalie/summary": "goalie_summary_20252026_2.json",
    "/stats/rest/en/team/summary": "team_summary_20252026_2.json",
    "/stats/rest/en/team": "team.json",
    "/stats/rest/en/franchise": "franchise.json",
    "/stats/rest/en/shiftcharts": "shiftcharts_2025020001.json",
    "/search/api/v1/search/player": "search_mcdavid.json",
}


def load(name: str) -> Any:
    """Return a recorded NHL response by fixture file name."""
    return json.loads((FIXTURES / name).read_text())


class _ReplayHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = ROUTES.get(parsed.path)
        if route is None:
            body = b'{"message":"Not Found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if isinstance(route, tuple):
            location = route[1] + (f"?{parsed.query}" if parsed.query else "")
            self.send_response(307)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = (FIXTURES / route).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "max-age=30")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="session")
def replay_server() -> Iterator[str]:
    """Serve recorded fixtures on localhost and yield the server root URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ReplayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def replay_env(root: str) -> dict[str, str]:
    """Environment variables pointing every NHL base URL at the replay server."""
    return {
        "NHL_WEB_BASE_URL": f"{root}/v1",
        "NHL_STATS_BASE_URL": f"{root}/stats/rest/en",
        "NHL_SEARCH_BASE_URL": f"{root}/search/api/v1",
    }


@pytest.fixture
def replay(replay_server: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the client at the replay server for one test."""
    for name, value in replay_env(replay_server).items():
        monkeypatch.setenv(name, value)
    return replay_server


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    api.clear_cache()
    yield
    api.clear_cache()
