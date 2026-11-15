"""Hash-checked real HTTP recordings; analytical transformations stay in visible SQL."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

ENVIRONMENTS = ("NHL_WEB_BASE_URL", "NHL_STATS_BASE_URL", "NHL_SEARCH_BASE_URL")


class NHLExample:
    """Own one bounded replay server, restoring inherited endpoints on cleanup."""

    def __init__(self, mode: str, scenario: str):
        if mode not in {"replay", "live"}:
            raise ValueError("DATA_MODE must be replay or live")
        if scenario not in {"shifts", "games", "season", "players"}:
            raise ValueError("Unknown NHL notebook scenario")
        self.mode = mode
        self.requests: list[str] = []
        self.unexpected: list[str] = []
        self.server = None
        self.thread = None
        self.previous = {key: os.environ.pop(key, None) for key in ENVIRONMENTS}
        if mode == "live":
            return
        root = Path(__file__).resolve().parent
        if scenario == "shifts":
            folder = root / "fixtures"
            manifest = json.loads((folder / "provenance.json").read_text())
            routes = [
                ("/v1/gamecenter/2025020001/play-by-play", {}),
                ("/stats/rest/en/shiftcharts", {"cayenneExp": "gameId=2025020001"}),
            ]
            items = [
                dict(item, request_path=path, params=params)
                for item, (path, params) in zip(manifest["files"], routes, strict=True)
            ]
        else:
            folder = root / "recordings"
            manifest = json.loads((folder / "provenance.json").read_text())
            prefixes = {"web": "/v1/", "stats": "/stats/rest/en/"}
            items = [
                dict(item, request_path=prefixes[item["host"]] + item["path"])
                for item in manifest["files"]
                if item["scenario"] == scenario
            ]
        self.expected = [item["file"] for item in items]
        responses = {}
        for item in items:
            body = (folder / item["file"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise ValueError("Recorded response hash mismatch: " + item["file"])
            key = (item["request_path"], tuple(sorted((k, str(v)) for k, v in item["params"].items())))
            responses[key] = (item["file"], body)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                route = urlparse(self.path)
                query = parse_qs(route.query, keep_blank_values=True)
                if any(len(values) != 1 for values in query.values()):
                    owner.unexpected.append("duplicate query values")
                    self.send_error(400)
                    return
                key = (route.path, tuple(sorted((k, v[0]) for k, v in query.items())))
                if key not in responses:
                    owner.unexpected.append(self.path)
                    self.send_error(404, "Outside recorded coverage")
                    return
                name, body = responses[key]
                owner.requests.append(name)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        endpoint = f"http://127.0.0.1:{self.server.server_port}"
        for key, suffix in zip(ENVIRONMENTS, ("v1", "stats/rest/en", "unsupported-search"), strict=True):
            os.environ[key] = endpoint + "/" + suffix

    def audit(self) -> str:
        """Require exactly one request for each declared response, without fallbacks."""
        if self.mode == "live":
            return "Live public requests used cleared endpoint overrides; no replay fallback."
        assert not self.unexpected, self.unexpected
        assert Counter(self.requests) == Counter(self.expected), (self.requests, self.expected)
        return f"Exactly {len(self.expected)} recorded HTTP responses requested once each; no unexpected requests."

    def close(self):
        """Stop the server and restore the environment owned by this run."""
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
