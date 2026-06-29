from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from plone.observability.interfaces import ILivenessCheck
from plone.observability.interfaces import IReadinessCheck
from socketserver import ThreadingMixIn
from zope.component import getUtilitiesFor

import json
import logging
import os
import sys
import threading


logger = logging.getLogger(__name__)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer that handles each request in a new thread."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            # Probe client disconnected before we finished writing the
            # response (common during warmup when readiness returns 503).
            # Harmless, so do not dump a traceback.
            logger.debug("Health probe connection dropped from %s", client_address)
            return
        super().handle_error(request, client_address)


class HealthRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for health probe endpoints."""

    def do_GET(self):
        if self.path == "/live":
            self._handle_live()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/startup":
            self._handle_startup()
        else:
            self.send_error(404)

    def _handle_live(self):
        checks = {}
        ok = True
        for name, check in getUtilitiesFor(ILivenessCheck):
            check_ok, message = check()
            checks[name] = {"ok": check_ok, "message": message}
            if not check_ok:
                ok = False
        self._send_json(
            200 if ok else 503, {"status": "ok" if ok else "failed", "checks": checks}
        )

    def _handle_ready(self):
        server = self.server
        checks = {}
        ok = True
        for name, check in getUtilitiesFor(IReadinessCheck):
            check_ok, message = check()
            checks[name] = {"ok": check_ok, "message": message}
            if not check_ok:
                ok = False
        if ok:
            server.health_server._started = True
        self._send_json(
            200 if ok else 503, {"status": "ok" if ok else "failed", "checks": checks}
        )

    def _handle_startup(self):
        started = self.server.health_server._started
        self._send_json(
            200 if started else 503,
            {"status": "ok" if started else "starting"},
        )

    def _send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Probe client disconnected before we finished writing (common
            # during warmup when readiness returns 503). Harmless.
            logger.debug("Health probe client disconnected early")

    def log_message(self, format, *args):  # noqa: A002 (stdlib override signature)
        # Suppress default stderr logging
        logger.debug(format, *args)


class HealthServer:
    """Manages the health check HTTP server on a separate daemon thread."""

    def __init__(self, host=None, port=None):
        self.host = host or os.environ.get("PLONE_OBSERVABILITY_HEALTH_HOST", "0.0.0.0")
        self.port = port or int(
            os.environ.get("PLONE_OBSERVABILITY_HEALTH_PORT", "8081")
        )
        self._started = False
        self._thread = None
        self._httpd = None
        self.db = None  # Set during startup to hold ZODB Database reference

    def start(self):
        if self.port == 0:
            logger.info("Health server disabled (port=0)")
            return
        try:
            self._httpd = ThreadingHTTPServer(
                (self.host, self.port), HealthRequestHandler
            )
        except OSError as exc:
            logger.error(
                "Health server could not bind %s:%s: %s", self.host, self.port, exc
            )
            self._httpd = None
            return
        self._httpd.health_server = self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="plone.observability.health",
            daemon=True,
        )
        self._thread.start()
        logger.info("Health server started on %s:%s", self.host, self.port)

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
        self._thread = None
