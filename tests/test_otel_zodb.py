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


def test_commit_noop_when_suppressed(
    span_exporter, monkeypatch, registered_commit_tracer
):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import exclusions

    import transaction

    token = exclusions.suppress_token()
    try:
        transaction.begin()
        transaction.commit()
    finally:
        exclusions.detach(token)
    assert span_exporter.get_finished_spans() == ()


def test_traced_setstate_accumulates_and_passes_through(monkeypatch):
    from plone.observability.otel import zodb

    clock = [0]
    monkeypatch.setattr("time.perf_counter_ns", lambda: clock[0])

    calls = []

    def original(self, obj):
        clock[0] += 500  # 500 ns elapsed during the load
        calls.append(obj)
        return "state"

    wrapped = zodb._traced_setstate(original)

    class _Conn:
        pass

    conn = _Conn()
    assert wrapped(conn, "obj1") == "state"
    assert conn._otel_load_time_ns == 500
    wrapped(conn, "obj2")
    assert conn._otel_load_time_ns == 1000
    assert calls == ["obj1", "obj2"]


def test_traced_setstate_records_time_on_exception(monkeypatch):
    from plone.observability.otel import zodb

    clock = [0]
    monkeypatch.setattr("time.perf_counter_ns", lambda: clock[0])

    def original(self, obj):
        clock[0] += 300
        raise ValueError("boom")

    wrapped = zodb._traced_setstate(original)
    conn = type("C", (), {})()
    with pytest.raises(ValueError):
        wrapped(conn, "obj")
    assert conn._otel_load_time_ns == 300


def test_register_patches_and_unregister_restores_setstate():
    from plone.observability.otel import zodb
    from ZODB.Connection import Connection

    original = Connection.setstate
    zodb.register()
    try:
        assert Connection.setstate is not original
        assert getattr(Connection.setstate, "_otel_wrapped", False)
    finally:
        zodb.unregister()
    assert Connection.setstate is original
