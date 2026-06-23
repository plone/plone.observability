import json
import os
import socket
import time
import urllib.request
from unittest import mock

import pytest

from plone.observability.health.server import HealthServer


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def health_server():
    port = _find_free_port()
    server = HealthServer(host="127.0.0.1", port=port)
    server.start()
    # Wait for server to be ready
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield server, port
    server.stop()


class TestHealthServer:
    def test_live_returns_200(self, health_server):
        server, port = health_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/live")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_ready_returns_200_no_checks(self, health_server):
        server, port = health_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/ready")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_startup_returns_200_after_ready(self, health_server):
        server, port = health_server
        # First hit /ready to mark as started
        urllib.request.urlopen(f"http://127.0.0.1:{port}/ready")
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/startup")
        assert resp.status == 200

    def test_unknown_path_returns_404(self, health_server):
        server, port = health_server
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
        assert exc_info.value.code == 404

    def test_server_is_daemon_thread(self, health_server):
        server, port = health_server
        assert server._thread.daemon is True

    def test_port_from_env(self):
        env = {"PLONE_OBSERVABILITY_HEALTH_PORT": "9999"}
        with mock.patch.dict(os.environ, env):
            server = HealthServer()
            assert server.port == 9999

    def test_disabled_with_port_zero(self):
        env = {"PLONE_OBSERVABILITY_HEALTH_PORT": "0"}
        with mock.patch.dict(os.environ, env):
            server = HealthServer()
            server.start()
            assert server._thread is None
            server.stop()


def test_start_is_non_fatal_on_bind_error(monkeypatch):
    from plone.observability.health import server as server_mod
    from plone.observability.health.server import HealthServer

    def boom(*args, **kwargs):
        raise OSError("Address already in use")

    monkeypatch.setattr(server_mod, "ThreadingHTTPServer", boom)
    hs = HealthServer(port=8099)
    hs.start()  # must not raise
    assert hs._httpd is None
