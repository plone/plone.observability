"""Tests for otel/rendering.py — viewlet/portlet render spans."""

from zope.interface import alsoProvides

import pytest


class _Conn:
    def __init__(self, loads=0, stores=0):
        self.loads = loads
        self.stores = stores

    def getTransferCounts(self, clear=False):
        return (self.loads, self.stores)


class _App:
    def __init__(self, jar):
        self._p_jar = jar


class _Req:
    def __init__(self, conn):
        self.PARENTS = [_App(conn)]


class _Viewlet:
    def __init__(self, name, html, conn=None, loads=0):
        self.__name__ = name
        self._html = html
        self._conn = conn
        self._loads = loads

    def render(self):
        if self._conn is not None:
            self._conn.loads += self._loads
        return self._html


@pytest.fixture(autouse=True)
def _unregister_after():
    yield
    from plone.observability.otel import rendering

    rendering.unregister()


def _make_manager(viewlets, request, name="plone.portalheader", head_iface=None):
    from zope.viewlet.manager import ViewletManagerBase

    class _FakeManager(ViewletManagerBase):
        def __init__(self):
            self.viewlets = viewlets
            self.request = request
            self.__name__ = name
            self.template = None

    mgr = _FakeManager()
    if head_iface is not None:
        alsoProvides(mgr, head_iface)
    return mgr


def test_viewlet_manager_and_viewlet_spans(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import rendering

    rendering.register()
    req = _Req(_Conn())
    mgr = _make_manager(
        [_Viewlet("plone.logo", "<a/>"), _Viewlet("plone.searchbox", "<form/>")],
        req,
        name="plone.portalheader",
    )
    out = mgr.render()

    assert out == "<a/>\n<form/>"  # original join preserved
    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    assert "viewletmanager plone.portalheader" in spans
    assert "viewlet plone.logo" in spans
    assert "viewlet plone.searchbox" in spans
    mgr_span = spans["viewletmanager plone.portalheader"]
    assert mgr_span.attributes["plone.viewletmanager.name"] == "plone.portalheader"
    assert mgr_span.attributes["plone.viewlet.count"] == 2
    # viewlet nests under manager
    child = spans["viewlet plone.logo"]
    assert child.parent is not None
    assert child.parent.span_id == mgr_span.context.span_id


def test_head_manager_has_no_viewlet_spans(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.app.layout.viewlets.interfaces import IHtmlHead
    from plone.observability.otel import rendering

    rendering.register()
    req = _Req(_Conn())
    mgr = _make_manager(
        [_Viewlet("plone.charset", "<meta/>")],
        req,
        name="plone.htmlhead",
        head_iface=IHtmlHead,
    )
    mgr.render()

    names = [s.name for s in span_exporter.get_finished_spans()]
    assert "viewletmanager plone.htmlhead" in names
    assert not any(n.startswith("viewlet ") for n in names)


def test_viewlet_span_carries_zodb_counts(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import rendering

    rendering.register()
    conn = _Conn()
    req = _Req(conn)
    mgr = _make_manager(
        [_Viewlet("plone.navigation", "<nav/>", conn=conn, loads=7)], req
    )
    mgr.render()

    span = next(
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "viewlet plone.navigation"
    )
    assert span.attributes["plone.zodb.objects_loaded"] == 7


def test_optout_disables_render_spans(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_RENDER", "0")
    from plone.observability.otel import rendering

    rendering.register()
    req = _Req(_Conn())
    mgr = _make_manager([_Viewlet("plone.logo", "<a/>")], req)
    assert mgr.render() == "<a/>"
    assert span_exporter.get_finished_spans() == ()


def test_register_idempotent_and_unregister_restores():
    from plone.observability.otel import rendering
    from zope.viewlet.manager import ViewletManagerBase

    original = ViewletManagerBase.render
    rendering.register()
    rendering.register()  # idempotent
    assert ViewletManagerBase.render is not original
    rendering.unregister()
    assert ViewletManagerBase.render is original
