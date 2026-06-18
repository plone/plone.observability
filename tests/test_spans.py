from plone.observability.spans import start_span


def test_start_span_records_span_and_attributes(span_exporter):
    with start_span("unit.test", {"foo": "bar"}) as span:
        assert span is not None
    finished = span_exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "unit.test"
    assert finished[0].attributes["foo"] == "bar"


def test_start_span_is_noop_without_opentelemetry(monkeypatch):
    import plone.observability.spans as spans

    monkeypatch.setattr(spans, "_trace", None)
    with start_span("unit.test") as span:
        assert span is None
