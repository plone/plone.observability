from plone.observability.health.server import HealthServer
from unittest import mock

import contextlib
import json
import logging
import os
import pytest
import socket
import threading
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


@contextlib.contextmanager
def _registered_check(check, name="test-readiness"):
    """Register *check* (an IReadinessCheck instance) in the global registry."""
    from plone.observability.interfaces import IReadinessCheck
    from zope.component import getGlobalSiteManager

    gsm = getGlobalSiteManager()
    gsm.registerUtility(check, IReadinessCheck, name=name)
    try:
        yield check
    finally:
        gsm.unregisterUtility(check, IReadinessCheck, name=name)


def _make_check_class():
    from plone.observability.interfaces import IReadinessCheck
    from zope.interface import implementer

    @implementer(IReadinessCheck)
    class ControlledCheck:
        """Counts runs; blocks while ``gate`` is cleared."""

        def __init__(self, ok=True, raises=False):
            self.ok = ok
            self.raises = raises
            self.calls = 0
            self.started = threading.Event()
            self.gate = threading.Event()
            self.gate.set()

        def __call__(self):
            self.calls += 1
            self.started.set()
            self.gate.wait(10)
            if self.raises:
                raise RuntimeError("boom")
            return self.ok, "controlled"

    return ControlledCheck


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def health_server():
    port = _find_free_port()
    server = HealthServer(host="127.0.0.1", port=port)
    # These tests swap checks between requests a few ms apart, so they need
    # every probe to run the checks. The result cache has its own tests.
    server.readiness_cache_ttl = 0
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


class TestSingleFlightReadiness:
    """#79: one readiness run at a time, probes never wait for it."""

    def _server(self, ttl=0, stuck_after=10):
        server = HealthServer(host="127.0.0.1", port=0)
        server.readiness_cache_ttl = ttl
        server.readiness_stuck_after = stuck_after
        return server

    def _run_in_thread(self, server):
        results = []
        thread = threading.Thread(
            target=lambda: results.append(server.check_readiness()), daemon=True
        )
        thread.start()
        return thread, results

    def test_settings_from_env(self):
        env = {
            "PLONE_OBSERVABILITY_READINESS_CACHE_TTL": "0.5",
            "PLONE_OBSERVABILITY_READINESS_STUCK_AFTER": "30",
        }
        with mock.patch.dict(os.environ, env):
            server = HealthServer(port=0)
        assert server.readiness_cache_ttl == 0.5
        assert server.readiness_stuck_after == 30

    def test_defaults(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("PLONE_OBSERVABILITY_READINESS_CACHE_TTL", None)
            os.environ.pop("PLONE_OBSERVABILITY_READINESS_STUCK_AFTER", None)
            server = HealthServer(port=0)
        assert server.readiness_cache_ttl == 2
        assert server.readiness_stuck_after == 10

    def test_concurrent_probes_run_the_check_once(self):
        server = self._server()
        with _registered_check(_make_check_class()()) as check:
            check.gate.clear()
            thread, results = self._run_in_thread(server)
            assert check.started.wait(5)

            # no previous result: every other probe gets an immediate 503
            for _ in range(5):
                ok, checks, message = server.check_readiness()
                assert ok is False
                assert "in progress" in message

            check.gate.set()
            thread.join(5)
        assert check.calls == 1
        assert results[0][0] is True

    def test_returns_last_result_while_a_fresh_run_is_in_progress(self):
        server = self._server()
        with _registered_check(_make_check_class()()) as check:
            assert server.check_readiness()[0] is True

            check.gate.clear()
            check.started.clear()
            thread, _ = self._run_in_thread(server)
            assert check.started.wait(5)

            ok, checks, message = server.check_readiness()
            assert ok is True
            assert checks["test-readiness"]["ok"] is True
            assert message is None

            check.gate.set()
            thread.join(5)
        assert check.calls == 2

    def test_stuck_run_answers_503_and_warns_once(self, caplog):
        server = self._server(stuck_after=0.05)
        with _registered_check(_make_check_class()()) as check:
            assert server.check_readiness()[0] is True

            check.gate.clear()
            check.started.clear()
            thread, _ = self._run_in_thread(server)
            assert check.started.wait(5)
            time.sleep(0.1)

            with caplog.at_level(logging.WARNING):
                first = server.check_readiness()
                second = server.check_readiness()

            check.gate.set()
            thread.join(5)
        for ok, checks, message in (first, second):
            assert ok is False
            assert checks == {}
            assert "in progress for" in message
        stuck = [r for r in caplog.records if "running for" in r.getMessage()]
        assert len(stuck) == 1
        assert check.calls == 2

    def test_result_is_cached_for_ttl(self):
        server = self._server(ttl=60)
        with _registered_check(_make_check_class()()) as check:
            assert server.check_readiness()[0] is True
            assert server.check_readiness()[0] is True
            assert check.calls == 1

            server.readiness_cache_ttl = 0
            server.check_readiness()
            assert check.calls == 2

    def test_failures_are_cached_too(self):
        server = self._server(ttl=60)
        with _registered_check(_make_check_class()(ok=False)) as check:
            assert server.check_readiness()[0] is False
            assert server.check_readiness()[0] is False
        assert check.calls == 1

    def test_raising_check_releases_the_flight(self):
        server = self._server()
        with _registered_check(_make_check_class()(raises=True)) as check:
            with pytest.raises(RuntimeError):
                server.check_readiness()
            check.raises = False
            assert server.check_readiness()[0] is True
        assert check.calls == 2

    def test_http_probes_do_not_wait_for_a_blocked_check(self, health_server):
        """/ready and /startup share the flight and answer within the
        kubelet timeout while a check hangs."""
        server, port = health_server
        with _registered_check(_make_check_class()()) as check:
            check.gate.clear()
            thread = threading.Thread(
                target=lambda: urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/ready", timeout=10
                ),
                daemon=True,
            )
            thread.start()
            assert check.started.wait(5)

            for path in ("/ready", "/startup", "/ready"):
                with pytest.raises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1)
                assert exc.value.code == 503
            body = json.loads(exc.value.read())
            assert "in progress" in body["message"]

            check.gate.set()
            thread.join(5)
        assert check.calls == 1
