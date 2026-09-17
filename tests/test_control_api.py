"""Tests for the app's read-only control API state."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.control_api import RouterState, make_handler


class RouterStateTests(unittest.TestCase):
    def test_health_and_redacted_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "options.json"
            config.write_text(
                json.dumps({"api_token": "secret", "sources": [{"id": "shed"}]}),
                encoding="utf-8",
            )
            state = RouterState(config, "0.1.0", Path(temp_dir) / "runtime")

            self.assertEqual(state.health()["status"], "ok")
            self.assertEqual(state.health()["version"], "0.1.0")
            self.assertEqual(state.config()["api_token"], "**REDACTED**")
            self.assertEqual(state.config()["sources"][0]["id"], "shed")

    def test_worker_status_checks_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "options.json"
            runtime = root / "runtime"
            runtime.mkdir()
            config.write_text("{}", encoding="utf-8")
            (runtime / "api.json").write_text(
                json.dumps({"id": "api", "pid": os.getpid(), "type": "control_api"}),
                encoding="utf-8",
            )
            (runtime / "dead.json").write_text(
                json.dumps({"id": "dead", "pid": 99999999, "type": "satellite"}),
                encoding="utf-8",
            )
            state = RouterState(config, "0.1.0", runtime)

            status = state.status()["workers"]
            self.assertTrue(status["api"]["running"])
            self.assertFalse(status["dead"]["running"])
            self.assertEqual(state.health()["status"], "degraded")

    def test_http_api_requires_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "options.json"
            config.write_text("{}", encoding="utf-8")
            state = RouterState(config, "0.1.0", Path(temp_dir) / "runtime")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, "secret"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/v1/health"
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(url, timeout=2)
                self.assertEqual(error.exception.code, 401)

                request = urllib.request.Request(
                    url, headers={"Authorization": "Bearer secret"}
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    payload = json.load(response)
                self.assertEqual(payload["status"], "ok")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
