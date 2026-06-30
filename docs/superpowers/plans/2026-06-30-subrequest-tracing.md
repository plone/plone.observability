# Subrequest Tile Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit one OTel span per `plone.subrequest` call so blocks/mosaic tiles become visible inside the otherwise-opaque `transform.plone.app.blocks.tiles` span.

**Architecture:** A new `otel/subrequest.py` with a wrapt function-wrapper around `subrequest()` plus `register()` that installs `wrapt.register_post_import_hook`s on the two caller modules. The wrapper opens a span named `subrequest <last-path-segment>`, parented on the active transform span (read from `request.environ[_SINGLE_SPAN_KEY]`) or the current context. Activation is wired into `otel/wsgi.py`'s serving-only filter, next to the existing zodb/catalog instrumentation.

**Tech Stack:** OpenTelemetry SDK, `wrapt` (via `opentelemetry-instrumentation`), `zope.globalrequest`, pytest with the repo's `span_exporter` (InMemorySpanExporter) fixture.

## Global Constraints

- Instrument by **module-name string** in post-import hooks; **no top-level `import plone.subrequest`** — the module is safe to load even when those packages are absent (hooks stay inert). Only hard import is `opentelemetry` (already gated by the `otel` subpackage).
- Use `wrapt.register_post_import_hook` (import-order independent) — `from plone.subrequest import subrequest` callers bind the original at their import time.
- Span name: `subrequest <segment>`, `<segment>` = last non-empty path segment of the URL with the query stripped; fall back to `subrequest`. High-cardinality detail (full URL) goes in attributes.
- Parent = active transform span on `request.environ["plone.observability.otel.transform_span"]` (the `_SINGLE_SPAN_KEY` constant from `otel/transformchain.py`), else current context.
- Wrapper must be a pure pass-through when `not is_enabled()` or `exclusions.is_suppressed()`, must never swallow exceptions, and must never alter subrequest behaviour.
- Commit messages end with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run tests with: `.venv/bin/pytest <path> -v` (no DB needed; enable tracing per-test via `monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")`).

## Verified facts (from the b6 codebase)

- Activation point: `otel/wsgi.py:make_filter` runs, when `provider.is_enabled()`: `provider.setup_tracing(); zodb.register(); catalog.instrument_catalog()`. (There is no `otel/startup.py` anymore.)
- `provider.is_enabled()` / `provider.TRACER_NAME == "plone.observability"`.
- `exclusions.is_suppressed()` exists.
- `transformchain._SINGLE_SPAN_KEY == "plone.observability.otel.transform_span"`; it holds the currently-running single-transform span (set in `on_before_single_transform`, popped in `on_after_single_transform`).
- The single production caller is `plone/app/blocks/utils.py` (`from plone.subrequest import subrequest`, called in `resolve()`); mosaic builds on blocks. Cache hits / `++resource++` short-circuit before calling `subrequest`.
- Tests: `span_exporter` fixture (conftest) yields an InMemory exporter with `.get_finished_spans()` and `.clear()`. Pattern: set `PLONE_OBSERVABILITY_OTEL_ENABLED=1`, drive code, assert on `s.name`, `s.attributes`, `s.parent.span_id`, `s.context.span_id`. Mirror `tests/test_otel_transformchain.py`.
- News: towncrier, fragments in `news/`, type `feature` → `news/43.feature`.

---

### Task 1: The span wrapper (`_span_name`, `_parent_context`, `_traced_subrequest`)

**Files:**
- Create: `src/plone/observability/otel/subrequest.py`
- Test: `tests/test_otel_subrequest.py`

**Interfaces:**
- Consumes: `provider.is_enabled`, `provider.TRACER_NAME`, `exclusions.is_suppressed`, `transformchain._SINGLE_SPAN_KEY`, `zope.globalrequest.getRequest`.
- Produces: `_traced_subrequest(wrapped, instance, args, kwargs)` (wrapt-style wrapper), `_span_name(url) -> str`, `_parent_context() -> Context|None`. Consumed by `register()` (Task 2).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_otel_subrequest.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_subrequest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'plone.observability.otel.subrequest'`.

- [ ] **Step 3: Write the module**

Create `src/plone/observability/otel/subrequest.py`:

```python
"""Span per plone.subrequest call, so blocks/mosaic tiles show in the trace.

plone.subrequest bypasses ZPublisher.publish and the WSGI server, so neither the
WSGI middleware nor the pubevent subscribers see it, and there is no subrequest
event to hook. We wrap the function (see register()). Each subrequest becomes a
span nested under the active transform span (the tiles transform), else under
the current context (the publish span).
"""

from opentelemetry import trace
from opentelemetry.trace import set_span_in_context
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME
from plone.observability.otel.transformchain import _SINGLE_SPAN_KEY
from urllib.parse import urlsplit
from zope.globalrequest import getRequest


def _span_name(url):
    path = urlsplit(url or "").path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    return f"subrequest {segment}" if segment else "subrequest"


def _parent_context():
    """Context nesting the span under the active transform span, else current."""
    request = getRequest()
    if request is not None:
        try:
            span = request.environ.get(_SINGLE_SPAN_KEY)
        except Exception:
            span = None
        if span is not None:
            return set_span_in_context(span)
    return None  # None -> start_as_current_span uses the current context


def _traced_subrequest(wrapped, instance, args, kwargs):
    if not is_enabled() or exclusions.is_suppressed():
        return wrapped(*args, **kwargs)
    url = args[0] if args else kwargs.get("url", "")
    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(
        _span_name(url), context=_parent_context()
    ) as span:
        span.set_attribute("http.url", url)
        span.set_attribute("http.method", "GET")
        try:
            response = wrapped(*args, **kwargs)
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(exc)
            raise
        status = getattr(response, "status", None)
        if isinstance(status, int):
            span.set_attribute("http.status_code", status)
        return response
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_subrequest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/plone/observability/otel/subrequest.py tests/test_otel_subrequest.py
git commit -m "feat(otel): span wrapper for plone.subrequest calls (#43)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(Pre-commit may reformat; if the commit aborts, `git add -u` the reformatted files and commit again — check the commit's own exit code, do not pipe it through `tail`.)

---

### Task 2: register() + wire activation + news fragment

**Files:**
- Modify: `src/plone/observability/otel/subrequest.py`
- Modify: `src/plone/observability/otel/wsgi.py`
- Create: `news/43.feature`
- Test: `tests/test_otel_subrequest.py`

**Interfaces:**
- Consumes: `_traced_subrequest` (Task 1).
- Produces: `register()` — idempotent; installs post-import hooks wrapping `subrequest` in `plone.app.blocks.utils` and `plone.subrequest`. Called from `otel/wsgi.py:make_filter`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_otel_subrequest.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_subrequest.py::test_register_is_idempotent tests/test_otel_subrequest.py::test_target_modules -v`
Expected: FAIL — `AttributeError: module 'plone.observability.otel.subrequest' has no attribute 'register' / '_TARGET_MODULES'`.

- [ ] **Step 3: Add `register()` to the module**

Append to `src/plone/observability/otel/subrequest.py` (and add `import wrapt` to the import block):

```python
import wrapt


_TARGET_MODULES = ("plone.app.blocks.utils", "plone.subrequest")
_registered = False


def register():
    """Wrap subrequest() in its caller modules via post-import hooks. Idempotent.

    Targets modules by name so this is safe even when plone.subrequest /
    plone.app.blocks are absent: the hooks stay inert until those modules import.
    """
    global _registered
    if _registered:
        return

    def _patch(module):
        try:
            wrapt.wrap_function_wrapper(module, "subrequest", _traced_subrequest)
        except Exception:
            # Module present but no subrequest attr (API drift) -- skip silently.
            pass

    for name in _TARGET_MODULES:
        wrapt.register_post_import_hook(_patch, name)
    _registered = True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_subrequest.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Wire activation into the WSGI filter**

In `src/plone/observability/otel/wsgi.py`, add the import and the `register()` call:

```python
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
from plone.observability.otel import catalog
from plone.observability.otel import exclusions
from plone.observability.otel import provider
from plone.observability.otel import subrequest
from plone.observability.otel import zodb


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter: activate tracing (serving only) and wrap the app."""
    if provider.is_enabled():
        provider.setup_tracing()
        zodb.register()
        catalog.instrument_catalog()
        subrequest.register()

    traced_app = OpenTelemetryMiddleware(app)

    def filtered(environ, start_response):
        if exclusions.is_excluded(environ.get("PATH_INFO", "")):
            return app(environ, start_response)
        return traced_app(environ, start_response)

    return filtered
```

- [ ] **Step 6: Create the news fragment**

Create `news/43.feature`:

```
Trace ``plone.subrequest``-rendered tiles: emit one span per subrequest, nested under the active transform span, when ``plone.subrequest`` is installed.  [jensens]
```

- [ ] **Step 7: Run the full otel test set**

Run: `.venv/bin/pytest tests/test_otel_subrequest.py tests/test_otel_wsgi.py -v`
Expected: PASS (subrequest module + wsgi filter unaffected).

- [ ] **Step 8: Commit**

```bash
git add src/plone/observability/otel/subrequest.py src/plone/observability/otel/wsgi.py news/43.feature tests/test_otel_subrequest.py
git commit -m "feat(otel): register subrequest tracing in the serving filter (#43)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- New `otel/subrequest.py`, soft/no-hard-import → Task 1 module + Task 2 `register` by string. ✓
- wrapt post-import hooks on both caller modules → Task 2 `register`. ✓
- Span name `subrequest <segment>` + attributes (`http.url`/`http.method`/`http.status_code`) → Task 1 `_span_name` + wrapper + tests. ✓
- Parent = transform span else current context → Task 1 `_parent_context` + nesting test. ✓
- No-op when disabled/suppressed; never swallow → Task 1 wrapper + tests. ✓
- Activation wired next to zodb/catalog → Task 2 Step 5. ✓
- No span on cache hit / resource (no subrequest call) → inherent (wrapper only fires on real calls); noted, no code needed. ✓
- News fragment (towncrier `feature`) → Task 2 Step 6. ✓
- Tests via InMemory `span_exporter` → both tasks. ✓

**Placeholder scan:** none.

**Type consistency:** `_traced_subrequest(wrapped, instance, args, kwargs)`, `_span_name(url)->str`, `_parent_context()->Context|None`, `_TARGET_MODULES` tuple, `register()` — consistent across module, `wsgi.py`, and tests. `_SINGLE_SPAN_KEY` imported from `transformchain` (single source of truth).
