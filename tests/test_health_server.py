from plone.observability.health.server import HealthServer
from unittest import mock

import contextlib
import json
import os
import pytest
import socket
import time
import urllib.request


@contextlib.contextmanager
def _registered_readiness(ok, message="x", name="test-readiness"):
    """Register a temporary IReadinessCheck utility in the global registry."""
    from plone.observability.interfaces import IReadinessCheck
    from zope.component import getGlobalSiteManager
    from zope.interface import implementer

    @implementer(IReadinessCheck)
    class _Check:
        def __call__(self):
            return ok, message

    gsm = getGlobalSiteManager()
    check = _Check()
    gsm.registerUtility(check, IReadinessCheck, name=name)
    try:
        yield
    finally:
        gsm.unregisterUtility(check, IReadinessCheck, name=name)


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

    def test_startup_returns_200_without_prior_ready(self, health_server):
        # /startup must turn green on its own: Kubernetes gates the readiness
        # probe behind a successful startup probe, so /ready is never polled
        # first. With no failing readiness checks, /startup is ready immediately.
        server, port = health_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/startup")
        assert resp.status == 200
        assert json.loads(resp.read())["status"] == "ok"

    def test_startup_evaluates_readiness_then_latches(self, health_server):
        server, port = health_server

        # readiness failing -> startup not ready yet
        with _registered_readiness(False):
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/startup")
            assert exc.value.code == 503

        # readiness now passes -> startup goes green WITHOUT /ready being polled
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/startup")
        assert resp.status == 200

        # latched: once started it stays green even if readiness later flaps
        with _registered_readiness(False):
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


def test_send_json_swallows_client_disconnect():
    from plone.observability.health.server import HealthRequestHandler

    handler = HealthRequestHandler.__new__(HealthRequestHandler)
    handler.send_response = mock.Mock()
    handler.send_header = mock.Mock()
    handler.end_headers = mock.Mock()
    handler.wfile = mock.Mock()
    handler.wfile.write.side_effect = BrokenPipeError(32, "Broken pipe")

    # Must not raise: client disconnected mid-write.
    handler._send_json(503, {"status": "failed"})


def test_handle_error_suppresses_connection_errors():
    from plone.observability.health.server import ThreadingHTTPServer

    server = ThreadingHTTPServer.__new__(ThreadingHTTPServer)
    with mock.patch("socketserver.BaseServer.handle_error") as base_handle_error:
        try:
            raise ConnectionResetError(104, "Connection reset by peer")
        except ConnectionResetError:
            server.handle_error("request", ("127.0.0.1", 12345))
    base_handle_error.assert_not_called()


def test_handle_error_delegates_other_errors():
    from plone.observability.health.server import ThreadingHTTPServer

    server = ThreadingHTTPServer.__new__(ThreadingHTTPServer)
    with mock.patch("socketserver.BaseServer.handle_error") as base_handle_error:
        try:
            raise ValueError("something else")
        except ValueError:
            server.handle_error("request", ("127.0.0.1", 12345))
    base_handle_error.assert_called_once()


def test_start_is_non_fatal_on_bind_error(monkeypatch):
    from plone.observability.health import server as server_mod
    from plone.observability.health.server import HealthServer

    def boom(*args, **kwargs):
        raise OSError("Address already in use")

    monkeypatch.setattr(server_mod, "ThreadingHTTPServer", boom)
    hs = HealthServer(port=8099)
    hs.start()  # must not raise
    assert hs._httpd is None
