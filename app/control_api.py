#!/usr/bin/env python3
"""Small versioned control API for the camera voice router."""

from __future__ import annotations

import argparse
import copy
import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class RouterState:
    """Thread-safe snapshot of router configuration and worker status."""

    def __init__(self, config_path: Path, version: str, runtime_dir: Path | None = None) -> None:
        self._config_path = config_path
        self._version = version
        self._started_at = time.time()
        self._runtime_dir = runtime_dir or Path("/data/runtime")
        self._lock = threading.Lock()
        self._workers: dict[str, dict[str, Any]] = {}

    def config(self) -> dict[str, Any]:
        """Return the effective app configuration with obvious secrets hidden."""
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            return {"error": str(err)}
        redacted = copy.deepcopy(data)
        for key in ("api_token", "password", "token"):
            if key in redacted:
                redacted[key] = "**REDACTED**"
        return redacted

    def health(self) -> dict[str, Any]:
        """Return process-level health information."""
        workers = self._read_workers()
        running = sum(1 for worker in workers.values() if worker["running"])
        return {
            "status": "ok" if running == len(workers) else "degraded",
            "version": self._version,
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "worker_count": len(workers),
            "running_worker_count": running,
        }

    def status(self) -> dict[str, Any]:
        """Return a snapshot of registered workers."""
        workers = self._read_workers()
        return {"workers": workers, "generated_at": time.time()}

    def _read_workers(self) -> dict[str, dict[str, Any]]:
        workers: dict[str, dict[str, Any]] = {}
        try:
            records = self._runtime_dir.glob("*.json")
        except OSError:
            records = []
        for path in records:
            worker: dict[str, Any] = {"id": path.stem}
            try:
                worker = json.loads(path.read_text(encoding="utf-8"))
                pid = int(worker["pid"])
                os.kill(pid, 0)
                worker["running"] = True
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                worker["running"] = False
            workers[str(worker.get("id", path.stem))] = worker
        return workers


def make_handler(state: RouterState, api_token: str) -> type[BaseHTTPRequestHandler]:
    """Build an HTTP handler bound to a router state instance."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "WakeMesh/1"

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"control-api: {fmt % args}", flush=True)

        def _authorized(self) -> bool:
            if not api_token:
                return True
            return self.headers.get("Authorization") == f"Bearer {api_token}"

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            endpoints = {
                "/v1/health": state.health,
                "/v1/status": state.status,
                "/v1/config": state.config,
            }
            callback = endpoints.get(self.path)
            if callback is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._json(HTTPStatus.OK, callback())

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--config", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--version", default="development")
    parser.add_argument("--token", default="")
    parser.add_argument("--runtime-dir", type=Path, default=Path("/data/runtime"))
    args = parser.parse_args()

    state = RouterState(args.config, args.version, args.runtime_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, args.token))
    print(f"WakeMesh control API listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
