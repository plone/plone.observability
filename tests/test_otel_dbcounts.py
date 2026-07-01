"""Tests for otel/dbcounts.py — per-span ZODB transfer-count attributes."""


class _Conn:
    def __init__(self, loads=0, stores=0):
        self.loads = loads
        self.stores = stores
        self.clear_args = []

    def getTransferCounts(self, clear=False):
        self.clear_args.append(clear)
        return (self.loads, self.stores)


class _App:
    def __init__(self, jar):
        self._p_jar = jar


class _Req:
    def __init__(self, conn):
        self.PARENTS = [_App(conn)] if conn is not None else []


class _Span:
    def __init__(self):
        self.attrs = {}

    def set_attribute(self, key, value):
        self.attrs[key] = value


def test_read_counts_peeks_without_reset():
    from plone.observability.otel import dbcounts

    conn = _Conn(loads=5, stores=2)
    assert dbcounts.read_counts(_Req(conn)) == (5, 2)
    assert conn.clear_args == [False]  # peek, never reset


def test_read_counts_none_without_connection():
    from plone.observability.otel import dbcounts

    assert dbcounts.read_counts(_Req(None)) is None
    assert dbcounts.read_counts(object()) is None  # no PARENTS at all


def test_annotate_sets_delta_including_zero():
    from plone.observability.otel import dbcounts

    span = _Span()
    dbcounts.annotate(span, (1, 1), (4, 1))
    assert span.attrs["plone.zodb.objects_loaded"] == 3
    assert span.attrs["plone.zodb.objects_stored"] == 0


def test_annotate_noop_on_none():
    from plone.observability.otel import dbcounts

    span = _Span()
    dbcounts.annotate(span, None, (4, 1))
    dbcounts.annotate(span, (1, 1), None)
    dbcounts.annotate(None, (1, 1), (4, 1))
    assert span.attrs == {}


class _Resp:
    def __init__(self, status=200):
        self.status = status


def test_subrequest_span_carries_zodb_counts(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr

    conn = _Conn()
    req = _Req(conn)
    req.environ = {}  # subrequest._parent_context reads request.environ
    monkeypatch.setattr(sr, "getRequest", lambda: req)

    def fake(url, **kw):
        conn.loads += 7  # the tile "loads" 7 objects
        return _Resp(200)

    sr._traced_subrequest(fake, None, ("/p/@@tile",), {})

    span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "subrequest @@tile"
    )
    assert span.attributes["plone.zodb.objects_loaded"] == 7
    assert span.attributes["plone.zodb.objects_stored"] == 0


def test_publish_span_carries_request_total(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import pubevents
    from ZPublisher.pubevents import PubStart
    from ZPublisher.pubevents import PubSuccess

    conn = _Conn()

    class _PubReq:
        def __init__(self):
            self.environ = {}
            self.PARENTS = [_App(conn)]
            self._data = {"PATH_INFO": "/news"}

        def get(self, key, default=None):
            return self._data.get(key, default)

    req = _PubReq()
    pubevents.on_pub_start(PubStart(req))
    conn.loads += 42  # whole-request object loads
    conn.stores += 3
    pubevents.on_pub_success(PubSuccess(req))

    span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "ZPublisher.publish"
    )
    assert span.attributes["plone.zodb.objects_loaded"] == 42
    assert span.attributes["plone.zodb.objects_stored"] == 3


def test_subrequest_error_path_sets_no_counts(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr

    conn = _Conn()
    req = _Req(conn)
    req.environ = {}
    monkeypatch.setattr(sr, "getRequest", lambda: req)

    def fake(url, **kw):
        conn.loads += 4  # increment so a wrong impl would wrongly annotate
        raise ValueError("tile error")

    import pytest

    with pytest.raises(ValueError, match="tile error"):
        sr._traced_subrequest(fake, None, ("/p/@@tile",), {})

    span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "subrequest @@tile"
    )
    assert span.status.status_code.name == "ERROR"
    assert "plone.zodb.objects_loaded" not in span.attributes
    assert "plone.zodb.objects_stored" not in span.attributes


def test_publish_total_covers_subrequest_delta(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import pubevents
    from plone.observability.otel import subrequest as sr
    from ZPublisher.pubevents import PubStart
    from ZPublisher.pubevents import PubSuccess

    conn = _Conn()

    class _PubReq:
        def __init__(self):
            self.environ = {}
            self.PARENTS = [_App(conn)]
            self._data = {"PATH_INFO": "/page"}

        def get(self, key, default=None):
            return self._data.get(key, default)

    pubreq = _PubReq()
    pubevents.on_pub_start(PubStart(pubreq))

    # subrequest uses the same shared conn via _Req
    subreq = _Req(conn)
    subreq.environ = {}
    monkeypatch.setattr(sr, "getRequest", lambda: subreq)

    def fake(url, **kw):
        conn.loads += 5  # tile loads 5 objects

    sr._traced_subrequest(fake, None, ("/p/@@tile",), {})

    conn.loads += 3  # additional non-subrequest work

    pubevents.on_pub_success(PubSuccess(pubreq))

    tile_span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "subrequest @@tile"
    )
    assert tile_span.attributes["plone.zodb.objects_loaded"] == 5

    publish_span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "ZPublisher.publish"
    )
    assert publish_span.attributes["plone.zodb.objects_loaded"] == 8  # 5 + 3
