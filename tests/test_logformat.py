from plone.observability.logformat import TraceContextFormatter

import logging


def _format():
    formatter = TraceContextFormatter("%(otelTraceID)s %(otelSpanID)s %(message)s")
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
    return formatter.format(record)


def test_formats_ids_of_current_span(span_exporter):
    from opentelemetry import trace

    with trace.get_tracer("test").start_as_current_span("request") as span:
        line = _format()
    context = span.get_span_context()
    assert line == f"{context.trace_id:032x} {context.span_id:016x} hello"


def test_formats_zero_outside_a_span(span_exporter):
    assert _format() == "0 0 hello"


def test_formats_zero_without_opentelemetry(monkeypatch):
    import plone.observability.logformat as logformat

    monkeypatch.setattr(logformat, "_trace", None)
    assert _format() == "0 0 hello"
