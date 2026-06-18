import pytest


@pytest.fixture
def registered_commit_tracer():
    from plone.observability.otel import zodb

    zodb.register()
    yield
    zodb.unregister()


def test_commit_emits_span(span_exporter, monkeypatch, registered_commit_tracer):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    import transaction

    transaction.begin()
    transaction.commit()

    spans = span_exporter.get_finished_spans()
    assert any(s.name == "transaction.commit" for s in spans)


def test_commit_noop_when_disabled(
    span_exporter, monkeypatch, registered_commit_tracer
):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    import transaction

    transaction.begin()
    transaction.commit()
    assert span_exporter.get_finished_spans() == ()
