"""Opt-in RSS growth per request and per tile subrequest (#94)."""

from plone.observability import rss
from plone.observability.metrics.providers import request

import logging
import pytest


MiB = 1024 * 1024


@pytest.fixture(autouse=True)
def _fresh_tracker(monkeypatch):
    monkeypatch.setattr(request, "rss_tracker", request.RSSGrowthTracker())


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_REQUEST_RSS", "1")


def fake_rss(monkeypatch, *values):
    readings = iter(values)
    monkeypatch.setattr(rss, "read", lambda: next(readings))


def run(environ=None, path="/Plone/front-page"):
    def app(environ, start_response):
        start_response("200 OK", [])
        return [b""]

    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": path, **(environ or {})}
    request.ObservabilityMiddleware(app)(environ, lambda s, h, e=None: None)


def growth_metrics():
    provider = request.RequestMetricProvider(None)
    return {
        (m.name, m.labels.get("le")): m.value
        for m in provider.collect()
        if m.name.startswith("plone_request_rss_growth_bytes")
    }


class TestSwitch:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("PLONE_OBSERVABILITY_REQUEST_RSS", raising=False)
        assert rss.enabled() is False

    def test_disabled_reads_nothing_and_emits_nothing(self, monkeypatch):
        monkeypatch.delenv("PLONE_OBSERVABILITY_REQUEST_RSS", raising=False)

        def boom():
            raise AssertionError("RSS read while disabled")

        monkeypatch.setattr(rss, "read", boom)
        run()
        assert growth_metrics() == {}


class TestRequestMetric:
    def test_records_growth(self, enabled, monkeypatch):
        fake_rss(monkeypatch, 100 * MiB, 103 * MiB)
        run()
        metrics = growth_metrics()
        assert metrics[("plone_request_rss_growth_bytes_count", None)] == 1
        assert metrics[("plone_request_rss_growth_bytes_sum", None)] == 3 * MiB
        assert metrics[("plone_request_rss_growth_bytes_bucket", "1048576")] == 0
        assert metrics[("plone_request_rss_growth_bytes_bucket", "4194304")] == 1
        assert metrics[("plone_request_rss_growth_bytes_bucket", "+Inf")] == 1

    def test_shrinking_counts_as_zero_growth(self, enabled, monkeypatch):
        # A negative observation would make _sum decrease, which a counter
        # must not do.
        fake_rss(monkeypatch, 100 * MiB, 90 * MiB)
        run()
        metrics = growth_metrics()
        assert metrics[("plone_request_rss_growth_bytes_sum", None)] == 0
        assert metrics[("plone_request_rss_growth_bytes_bucket", "0")] == 1

    def test_no_reading_without_proc(self, enabled, monkeypatch):
        fake_rss(monkeypatch, None, None)
        run()
        assert growth_metrics()[("plone_request_rss_growth_bytes_count", None)] == 0

    def test_metric_types(self, enabled, monkeypatch):
        fake_rss(monkeypatch, 0, 1)
        run()
        metrics = [
            m
            for m in request.RequestMetricProvider(None).collect()
            if m.name.startswith("plone_request_rss_growth_bytes")
        ]
        assert {m.type for m in metrics} == {"counter"}
        assert {m.scope for m in metrics} == {"instance"}


class TestWarning:
    def test_warns_above_threshold_without_query_string(
        self, enabled, monkeypatch, caplog
    ):
        fake_rss(monkeypatch, 100 * MiB, 130 * MiB)
        with caplog.at_level(logging.WARNING, logger=request.logger.name):
            run({"QUERY_STRING": "token=secret"}, path="/Plone/passwordreset/abc")
        (record,) = caplog.records
        message = record.getMessage()
        assert "30.0 MiB" in message
        assert "GET /Plone/passwordreset/abc" in message
        assert "secret" not in message

    def test_quiet_below_threshold(self, enabled, monkeypatch, caplog):
        fake_rss(monkeypatch, 100 * MiB, 110 * MiB)
        with caplog.at_level(logging.WARNING, logger=request.logger.name):
            run()
        assert caplog.records == []

    def test_threshold_is_configurable(self, enabled, monkeypatch, caplog):
        monkeypatch.setenv("PLONE_OBSERVABILITY_REQUEST_RSS_WARN_MIB", "5")
        fake_rss(monkeypatch, 100 * MiB, 110 * MiB)
        with caplog.at_level(logging.WARNING, logger=request.logger.name):
            run()
        assert len(caplog.records) == 1

    def test_threshold_zero_disables_the_warning(self, enabled, monkeypatch, caplog):
        monkeypatch.setenv("PLONE_OBSERVABILITY_REQUEST_RSS_WARN_MIB", "0")
        fake_rss(monkeypatch, 100 * MiB, 900 * MiB)
        with caplog.at_level(logging.WARNING, logger=request.logger.name):
            run()
        assert caplog.records == []


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class TestAnnotate:
    def test_sets_start_end_and_delta(self):
        span = FakeSpan()
        rss.annotate(span, 100, 70)
        assert span.attributes == {
            "plone.process.rss_start_bytes": 100,
            "plone.process.rss_end_bytes": 70,
            "plone.process.rss_delta_bytes": -30,  # spans keep the sign
        }

    def test_skips_missing_readings(self):
        span = FakeSpan()
        rss.annotate(span, None, None)
        assert span.attributes == {}


ENVIRON = {
    "REQUEST_METHOD": "GET",
    "PATH_INFO": "/",
    "SERVER_NAME": "localhost",
    "SERVER_PORT": "80",
    "wsgi.url_scheme": "http",
}


def server_span(span_exporter):
    (span,) = [s for s in span_exporter.get_finished_spans() if s.kind.name == "SERVER"]
    return span


class TestRequestSpan:
    def _serve(self):
        from plone.observability.otel.wsgi import make_filter

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        wrapped = make_filter(app, {})
        b"".join(wrapped(dict(ENVIRON), lambda status, headers, exc=None: None))

    def test_server_span_carries_rss(self, span_exporter, enabled, monkeypatch):
        fake_rss(monkeypatch, 100 * MiB, 102 * MiB)
        self._serve()
        attributes = server_span(span_exporter).attributes
        assert attributes["plone.process.rss_delta_bytes"] == 2 * MiB
        assert attributes["plone.process.rss_start_bytes"] == 100 * MiB

    def test_no_attributes_when_disabled(self, span_exporter, monkeypatch):
        monkeypatch.delenv("PLONE_OBSERVABILITY_REQUEST_RSS", raising=False)
        self._serve()
        attributes = server_span(span_exporter).attributes
        assert "plone.process.rss_delta_bytes" not in attributes


class TestSubrequestSpan:
    def _call(self):
        from plone.observability.otel.subrequest import _traced_subrequest

        class Response:
            status = 200

        return _traced_subrequest(lambda url, **kw: Response(), None, ("/a/@@t",), {})

    def test_subrequest_span_carries_rss(self, span_exporter, enabled, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
        fake_rss(monkeypatch, 100 * MiB, 101 * MiB)
        self._call()
        (span,) = span_exporter.get_finished_spans()
        assert span.attributes["plone.process.rss_delta_bytes"] == MiB

    def test_no_attributes_when_disabled(self, span_exporter, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
        monkeypatch.delenv("PLONE_OBSERVABILITY_REQUEST_RSS", raising=False)
        self._call()
        (span,) = span_exporter.get_finished_spans()
        assert "plone.process.rss_delta_bytes" not in span.attributes
