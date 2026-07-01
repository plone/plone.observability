"""Render-phase spans: viewlet managers, viewlets, portlet columns, portlets.

Template rendering has no events, so we monkeypatch the two render methods (the
sanctioned pattern, cf. otel/catalog.py). Both can render via a template (the
children's render() runs inside the template) or via a direct join, so the
traced render wraps each transient child instance's render() and then calls the
original -- each child wrapper opens a span nested under the manager/column span.
"""

from plone.base.utils import boolean_value
from plone.observability.otel import dbcounts
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.spans import start_span

import os


# list of (cls, name, original) we replaced, for unregister
_patched = []

_HEAD_INTERFACE_NAMES = ("IHTTPHeaders", "IHtmlHead", "IHtmlHeadLinks", "IScripts")


def _render_enabled():
    return boolean_value(
        os.environ.get("PLONE_OBSERVABILITY_OTEL_RENDER", ""), default=True
    )


def _active():
    return is_enabled() and not exclusions.is_suppressed() and _render_enabled()


def _is_head_manager(manager):
    try:
        from plone.app.layout.viewlets import interfaces as vi
    except ImportError:
        return False
    for iface_name in _HEAD_INTERFACE_NAMES:
        iface = getattr(vi, iface_name, None)
        if iface is not None and iface.providedBy(manager):
            return True
    return False


def _wrap_child_render(child, request, span_name):
    """Replace ``child.render`` with a span-emitting wrapper (transient object)."""
    original_render = child.render

    def traced(*args, **kwargs):
        before = dbcounts.read_counts(request)
        with start_span(span_name) as span:
            html = original_render(*args, **kwargs)
            if span is not None:
                dbcounts.annotate(span, before, dbcounts.read_counts(request))
            return html

    child.render = traced


def _traced_viewletmanager_render(original):
    def render(self):
        if not _active():
            return original(self)
        name = getattr(self, "__name__", "") or type(self).__name__
        request = getattr(self, "request", None)
        before = dbcounts.read_counts(request)
        with start_span(f"viewletmanager {name}") as span:
            viewlets = getattr(self, "viewlets", None) or []
            if not _is_head_manager(self):
                for viewlet in viewlets:
                    vname = getattr(viewlet, "__name__", "") or type(viewlet).__name__
                    _wrap_child_render(viewlet, request, f"viewlet {vname}")
            result = original(self)
            if span is not None:
                span.set_attribute("plone.viewletmanager.name", name)
                span.set_attribute("plone.viewlet.count", len(viewlets))
                dbcounts.annotate(span, before, dbcounts.read_counts(request))
            return result

    return render


def _traced_portletmanager_render(original):
    def render(self):
        if not _active():
            return original(self)
        manager = getattr(self, "manager", None)
        name = getattr(manager, "__name__", "") or type(self).__name__
        request = getattr(self, "request", None)
        before = dbcounts.read_counts(request)
        with start_span(f"portletcolumn {name}") as span:
            try:
                portlets = self.portletsToShow()
            except Exception:
                portlets = []
            for p in portlets:
                renderer = p.get("renderer")
                if renderer is None:
                    continue
                pname = p.get("name") or type(renderer).__name__
                _wrap_child_render(renderer, request, f"portlet {pname}")
            result = original(self)
            if span is not None:
                span.set_attribute("plone.portletmanager.name", name)
                dbcounts.annotate(span, before, dbcounts.read_counts(request))
            return result

    return render


def _patch(cls, attr, make_wrapper):
    original = cls.__dict__.get(attr) or getattr(cls, attr, None)
    if original is None or getattr(original, "_otel_wrapped", False):
        return
    wrapper = make_wrapper(original)
    wrapper._otel_wrapped = True
    wrapper._otel_original = original
    setattr(cls, attr, wrapper)
    _patched.append((cls, attr, original))


def _patch_viewlets():
    try:
        from zope.viewlet.manager import ViewletManagerBase
    except ImportError:
        return
    _patch(ViewletManagerBase, "render", _traced_viewletmanager_render)


def _patch_portlets():
    try:
        from plone.portlets.manager import PortletManagerRenderer
    except ImportError:
        return
    _patch(PortletManagerRenderer, "render", _traced_portletmanager_render)


def register():
    if _patched:
        return
    _patch_viewlets()
    _patch_portlets()


def unregister():
    while _patched:
        cls, attr, original = _patched.pop()
        setattr(cls, attr, original)
