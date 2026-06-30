"""Tests for otel/subrequest.py — span per plone.subrequest call."""

from opentelemetry import trace

import pytest


class _Resp:
    def __init__(self, status=200):
        self.status = status


def _call(url="/a/b/@@tile", response=None, raises=None):
    """Invoke the wrapt wrapper directly around a fake subrequest()."""
    from plone.observability.otel.subrequest import _traced_subrequest

    def fake(u, **kw):
        if raises is not None:
            raise raises
        return response if response is not None else _Resp()

    return _traced_subrequest(fake, None, (url,), {})


def test_span_name_derivation():
    from plone.observability.otel.subrequest import _span_name

    assert _span_name("/a/b/@@tile?x=1") == "subrequest @@tile"
    assert _span_name("/a/b/") == "subrequest b"
    assert _span_name("/") == "subrequest"
    assert _span_name("") == "subrequest"


def test_emits_span_with_attributes(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    url = "/aaf/en/page/@@plone.app.standardtiles.html?x=1"
    resp = _call(url=url, response=_Resp(200))

    assert resp.status == 200
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "subrequest @@plone.app.standardtiles.html"
    assert span.attributes["http.url"] == url
    assert span.attributes["http.method"] == "GET"
    assert span.attributes["http.status_code"] == 200


def test_nests_under_transform_span(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr
    from plone.observability.otel.transformchain import _SINGLE_SPAN_KEY

    transform_span = trace.get_tracer("test").start_span(
        "transform.plone.app.blocks.tiles"
    )

    class _Req:
        environ = {_SINGLE_SPAN_KEY: transform_span}

    monkeypatch.setattr(sr, "getRequest", lambda: _Req())
    _call(url="/p/@@tile", response=_Resp(200))
    transform_span.end()

    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    child = spans["subrequest @@tile"]
    assert child.parent is not None
    assert child.parent.span_id == transform_span.context.span_id


def test_noop_when_disabled(span_exporter, monkeypatch):
    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)

    resp = _call(response=_Resp(204))
    assert resp.status == 204
    assert span_exporter.get_finished_spans() == ()


def test_noop_when_suppressed(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr

    monkeypatch.setattr(sr.exclusions, "is_suppressed", lambda: True)
    _call(response=_Resp(200))
    assert span_exporter.get_finished_spans() == ()


def test_exception_records_and_reraises(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")

    with pytest.raises(ValueError):
        _call(raises=ValueError("boom"))

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"


def test_register_is_idempotent():
    from plone.observability.otel import subrequest as sr

    sr.register()
    sr.register()  # must not raise


def test_wraps_a_caller_module(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr

    import types
    import wrapt

    mod = types.ModuleType("fake_caller")

    def original(url, **kw):
        return _Resp(200)

    mod.subrequest = original
    wrapt.wrap_function_wrapper(mod, "subrequest", sr._traced_subrequest)

    resp = mod.subrequest("/x/@@tile")
    assert resp.status == 200
    assert [s.name for s in span_exporter.get_finished_spans()] == ["subrequest @@tile"]


def test_target_modules():
    from plone.observability.otel import subrequest as sr

    assert sr._TARGET_MODULES == ("plone.app.blocks.utils", "plone.subrequest")
