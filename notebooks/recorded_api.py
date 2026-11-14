"""Replay two unchanged repository responses through supported NHL URL overrides."""

from __future__ import annotations

import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

ENVIRONMENTS = ("NHL_WEB_BASE_URL", "NHL_STATS_BASE_URL", "NHL_SEARCH_BASE_URL")


class RecordedAPI:
    """Serve only the documented game and shift-chart requests on loopback."""

    def __init__(self):
        """Verify fixture hashes and start a bounded local server."""
        manifest = json.loads(Path("fixtures/provenance.json").read_text())
        responses = {}
        for item in manifest["files"]:
            body = (Path("fixtures") / item["file"]).read_bytes()
            assert hashlib.sha256(body).hexdigest() == item["sha256"], "Fixture hash mismatch"
            responses[item["file"]] = body

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                route = urlparse(self.path)
                query = parse_qs(route.query)
                name = None
                if route.path == "/v1/gamecenter/2025020001/play-by-play" and not query:
                    name = "play_by_play_2025020001.json"
                elif route.path == "/stats/rest/en/shiftcharts" and query == {"cayenneExp": ["gameId=2025020001"]}:
                    name = "shiftcharts_2025020001.json"
                if name is None:
                    self.send_error(404, "Outside recorded fixture coverage")
                    return
                body = responses[name]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=60")
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        root = f"http://127.0.0.1:{self.server.server_port}"
        for key, suffix in zip(ENVIRONMENTS, ("v1", "stats/rest/en", "unsupported-search"), strict=True):
            os.environ[key] = f"{root}/{suffix}"

    def close(self):
        """Stop the server and remove its URL overrides."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for key in ENVIRONMENTS:
            os.environ.pop(key, None)


def configure(mode):
    """Clear inherited URL overrides; live failures never select replay."""
    if mode not in {"replay", "live"}:
        raise ValueError("DATA_MODE must be replay or live")
    for key in ENVIRONMENTS:
        os.environ.pop(key, None)
    return RecordedAPI() if mode == "replay" else None
