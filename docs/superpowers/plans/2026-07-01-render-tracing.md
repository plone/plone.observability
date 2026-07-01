# ClassicUI render-phase tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit OTel spans per viewlet manager, per body viewlet, per portlet column and per portlet (head managers collapse to a single span), each carrying the b14 per-span ZODB counts, so ClassicUI render cost is visible in traces.

**Architecture:** A new `otel/rendering.py` monkeypatches two render methods (the sanctioned pattern from `otel/catalog.py`): `zope.viewlet.manager.ViewletManagerBase.render` and `plone.portlets.manager.PortletManagerRenderer.render`. Because both can render via a template (children `render()` inside the template) or via a direct join, the traced render wraps each *child instance*'s `render` (transient per-request objects — no restore needed) and then calls the original render; each child wrapper opens its own span nested under the manager/column span (which is current). Spans reuse `otel/dbcounts.py` for the ZODB delta.

**Tech Stack:** OpenTelemetry, `plone.observability.spans.start_span`, `otel/dbcounts.py`, pytest with the repo's `span_exporter` fixture.

## Global Constraints

- Span names (low-cardinality; static registry): `viewletmanager <name>`, `viewlet <name>`, `portletcolumn <name>`, `portlet <name>`.
- Attributes: `plone.viewletmanager.name` + `plone.viewlet.count`; `plone.viewlet.name`; `plone.portletmanager.name`; `plone.portlet.name`. Plus `plone.zodb.objects_loaded`/`plone.zodb.objects_stored` on every render span via `dbcounts.annotate`.
- Head managers → manager span only, no per-viewlet spans. Head = provides one of `IHTTPHeaders`, `IHtmlHead`, `IHtmlHeadLinks`, `IScripts` (from `plone.app.layout.viewlets.interfaces`).
- Gate every traced method on `is_enabled()` and NOT `exclusions.is_suppressed()` and the opt-out `PLONE_OBSERVABILITY_OTEL_RENDER` (default on; `0`/`false` disables render spans only).
- Sanctioned-monkeypatch pattern like `otel/catalog.py`: module-level `_patched` list of `(cls, name, original)`, `register()` (idempotent) + `unregister()` (restores). Soft-dependency: patch a target only when its class imports.
- Never break rendering: a traced method degrades to the original on any error; child instances are transient so their wrapped `render` is not restored.
- No view-render span (deferred). No per-macro/expression spans.
- Commit footer exactly: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run tests: `.venv/bin/pytest <path> -v`. Before committing run `uvx pre-commit run --all-files` (this clone has no pre-commit installed; CI's `qa` runs ruff + ruff-format + zpretty — plain `ruff check` is not enough).

## Verified facts (installed packages)

- `zope.viewlet.manager.ViewletManagerBase.render`: `if self.template: return self.template(viewlets=self.viewlets)` else `return '\n'.join([viewlet.render() for viewlet in self.viewlets])`. `plone.app.viewletmanager` overrides only `filter/sort/update`, so `render` has this single definition. Viewlets in `self.viewlets` have `__name__` (set in `update()`), are acquisition-wrapped, and are per-request instances.
- `plone.portlets.manager.PortletManagerRenderer.render`: `portlets = self.portletsToShow(); if self.template: return self.template(portlets=portlets) else return "\n".join([p["renderer"].render() for p in portlets])`. `ColumnPortletManagerRenderer` (plone.app.portlets) sets `template = column.pt`. `portletsToShow()` is memoized (same renderer instances across calls). Each item `p` is a dict with `p["renderer"]` and `p["name"]`. The manager object is `self.manager` (an `IPortletManager` with `__name__` like `plone.leftcolumn`).
- `plone.observability.spans.start_span(name, attributes=None)` is a context manager yielding the span (or None); it uses `start_as_current_span`, so children nest under the currently-open span.
- `otel/dbcounts.py`: `read_counts(request) -> (loads, stores)|None`, `annotate(span, before, after)` (no-op on None; sets `plone.zodb.objects_*`).
- Activation: `otel/wsgi.py:make_filter` calls, when `provider.is_enabled()`: `provider.setup_tracing(); zodb.register(); catalog.instrument_catalog(); subrequest.register()`.
- Head interfaces exist in `plone.app.layout.viewlets.interfaces`: `IHTTPHeaders`, `IHtmlHead`, `IHtmlHeadLinks`, `IScripts`.

---

### Task 1: `otel/rendering.py` — viewlet manager + viewlet spans

**Files:**
- Create: `src/plone/observability/otel/rendering.py`
- Test: `tests/test_otel_rendering.py`

**Interfaces:**
- Consumes: `spans.start_span`, `dbcounts.read_counts`/`annotate`, `provider.is_enabled`, `exclusions.is_suppressed`.
- Produces: `register()` / `unregister()` (viewlet patch so far); helpers `_render_enabled()`, `_active()`, `_is_head_manager(manager)`, `_wrap_child_render(child, request, span_name)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_otel_rendering.py`:

```python
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
        [_Viewlet("plone.charset", "<meta/>")], req,
        name="plone.htmlhead", head_iface=IHtmlHead,
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
        s for s in span_exporter.get_finished_spans() if s.name == "viewlet plone.navigation"
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
    from zope.viewlet.manager import ViewletManagerBase
    from plone.observability.otel import rendering

    original = ViewletManagerBase.render
    rendering.register()
    rendering.register()  # idempotent
    assert ViewletManagerBase.render is not original
    rendering.unregister()
    assert ViewletManagerBase.render is original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_rendering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'plone.observability.otel.rendering'`.

- [ ] **Step 3: Write the module (viewlet part)**

Create `src/plone/observability/otel/rendering.py`:

```python
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


def register():
    if _patched:
        return
    _patch_viewlets()


def unregister():
    while _patched:
        cls, attr, original = _patched.pop()
        setattr(cls, attr, original)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_rendering.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

```bash
uvx pre-commit run --files src/plone/observability/otel/rendering.py tests/test_otel_rendering.py
git add src/plone/observability/otel/rendering.py tests/test_otel_rendering.py
git commit -m "feat(otel): viewlet manager + viewlet render spans

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(Check the commit's own exit code.)

---

### Task 2: Portlet column + portlet spans

**Files:**
- Modify: `src/plone/observability/otel/rendering.py`
- Test: `tests/test_otel_rendering.py`

**Interfaces:**
- Consumes: `_wrap_child_render`, `_active`, `dbcounts`, `start_span` (Task 1).
- Produces: `_traced_portletmanager_render`, extends `register()` to patch `PortletManagerRenderer.render`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_otel_rendering.py`:

```python
class _PortletRenderer:
    def __init__(self, html, conn=None, loads=0):
        self._html = html
        self._conn = conn
        self._loads = loads

    def render(self):
        if self._conn is not None:
            self._conn.loads += self._loads
        return self._html


def _make_portlet_manager(portlets, request, column="plone.leftcolumn"):
    from plone.portlets.manager import PortletManagerRenderer

    class _Mgr:
        __name__ = column

    class _FakePortletRenderer(PortletManagerRenderer):
        def __init__(self):
            self.request = request
            self.manager = _Mgr()
            self.template = None
            self._portlets = portlets

        def portletsToShow(self):
            return self._portlets

    return _FakePortletRenderer()


def test_portlet_column_and_portlet_spans(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import rendering

    rendering.register()
    conn = _Conn()
    req = _Req(conn)
    mgr = _make_portlet_manager(
        [
            {"name": "navigation", "renderer": _PortletRenderer("<nav/>", conn=conn, loads=5)},
            {"name": "recent", "renderer": _PortletRenderer("<ul/>")},
        ],
        req,
    )
    out = mgr.render()

    assert out == "<nav/>\n<ul/>"
    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    assert spans["portletcolumn plone.leftcolumn"].attributes["plone.portletmanager.name"] == "plone.leftcolumn"
    assert "portlet navigation" in spans
    assert spans["portlet navigation"].attributes["plone.zodb.objects_loaded"] == 5
    assert spans["portlet navigation"].parent.span_id == spans["portletcolumn plone.leftcolumn"].context.span_id
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_otel_rendering.py::test_portlet_column_and_portlet_spans -v`
Expected: FAIL — no `portletcolumn …` span (portlet render not patched yet).

- [ ] **Step 3: Add the portlet patch**

In `src/plone/observability/otel/rendering.py`, add the traced portlet render and patch:

```python
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


def _patch_portlets():
    try:
        from plone.portlets.manager import PortletManagerRenderer
    except ImportError:
        return
    _patch(PortletManagerRenderer, "render", _traced_portletmanager_render)
```

And extend `register()`:

```python
def register():
    if _patched:
        return
    _patch_viewlets()
    _patch_portlets()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_rendering.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint + commit**

```bash
uvx pre-commit run --files src/plone/observability/otel/rendering.py tests/test_otel_rendering.py
git add src/plone/observability/otel/rendering.py tests/test_otel_rendering.py
git commit -m "feat(otel): portlet column + portlet render spans

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire activation + news fragment

**Files:**
- Modify: `src/plone/observability/otel/wsgi.py`
- Create: `news/+render-tracing.feature`
- Test: (full suite)

**Interfaces:**
- Consumes: `rendering.register` (Tasks 1–2).

- [ ] **Step 1: Wire into the WSGI filter**

In `src/plone/observability/otel/wsgi.py`, add the import and the `register()` call next to the others:

```python
from plone.observability.otel import catalog
from plone.observability.otel import exclusions
from plone.observability.otel import provider
from plone.observability.otel import rendering
from plone.observability.otel import subrequest
from plone.observability.otel import zodb
```

and inside `make_filter`, in the `if provider.is_enabled():` block:

```python
    if provider.is_enabled():
        provider.setup_tracing()
        zodb.register()
        catalog.instrument_catalog()
        subrequest.register()
        rendering.register()
```

- [ ] **Step 2: Create the news fragment**

Create `news/+render-tracing.feature`:

```
Trace the ClassicUI render phase: emit spans per viewlet manager, per body viewlet, per portlet column and per portlet (head viewlet managers collapse to a single span), each carrying the per-span ZODB object-load counts. Disable with ``PLONE_OBSERVABILITY_OTEL_RENDER=0``.
```

- [ ] **Step 3: Full suite + lint**

Run: `.venv/bin/pytest -q` → expected all pass (new render tests + existing suite; the `unregister()` autouse fixture keeps the patch from leaking).
Run: `uvx pre-commit run --all-files` → expected all hooks pass.

- [ ] **Step 4: Commit**

```bash
git add src/plone/observability/otel/wsgi.py news/+render-tracing.feature
git commit -m "feat(otel): register render tracing in the serving filter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Viewlet manager + body-viewlet spans; head managers collapse → Task 1 (`_traced_viewletmanager_render`, `_is_head_manager`) + tests. ✓
- Portlet column + portlet spans → Task 2 + test. ✓
- Per-span ZODB counts on all render spans → `dbcounts.annotate` in both traced renders + child wrapper + tests. ✓
- Template-vs-join robustness → child-instance `render` wrapping (works for both) + assertions on real `ViewletManagerBase`/`PortletManagerRenderer` subclasses. ✓
- Span names & attributes exact → Global Constraints + tests. ✓
- Opt-out + disabled/suppressed → `_active()`/`_render_enabled()` + `test_optout_disables_render_spans`. ✓
- Sanctioned monkeypatch, register/unregister, soft-dependency → `_patch`/`register`/`unregister` + idempotency/restore test. ✓
- Wire into activation → Task 3. ✓
- News fragment → Task 3. ✓
- No view-render span; no macro spans → nothing added for them. ✓

**Placeholder scan:** none (the `50`/`+render-tracing` fragment name is an explicit, resolved instruction, not a TODO).

**Type consistency:** `_active()`, `_is_head_manager(manager)`, `_wrap_child_render(child, request, span_name)`, `_patch(cls, attr, make_wrapper)`, `register()`/`unregister()`, and the two `_traced_*_render(original)` factories are used consistently across Tasks 1–3 and the tests. Span names/attributes match the Global Constraints block verbatim.
