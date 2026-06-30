# Per-span ZODB load/store counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record `plone.zodb.objects_loaded` / `plone.zodb.objects_stored` per span on the `ZPublisher.publish` span (request total) and each `subrequest` span (per-tile delta), so N+1 object-load cost is visible in traces.

**Architecture:** A small `otel/dbcounts.py` helper peeks `Connection.getTransferCounts(False)` (no reset) from the request's main connection (`request.PARENTS[-1]._p_jar`) and sets the start→end delta as span attributes. Wired into the existing `pubevents.py` publish-span lifecycle and the `subrequest.py` wrapper.

**Tech Stack:** ZODB `Connection.getTransferCounts`, OpenTelemetry span attributes, `zope.globalrequest`, pytest with the repo's `span_exporter` fixture.

## Global Constraints

- Attribute names (locked): `plone.zodb.objects_loaded`, `plone.zodb.objects_stored`. **Always set both**, even when the delta is 0.
- Peek with `getTransferCounts(False)` (no reset). The process-wide `LoadStoreActivityMonitor` resets with `(True)` only on connection close (after spans end) — do not disturb it.
- Connection = `request.PARENTS[-1]._p_jar` (main DB). Subrequests share the parent's connection. Multi-DB mounts are out of scope.
- Fully defensive: missing PARENTS/`_p_jar`/counts → no attributes; never affect the request or tracing.
- Scope: only the `ZPublisher.publish` and `subrequest` spans. No transform/commit spans. Process counters unchanged.
- Commit messages end with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run tests: `.venv/bin/pytest <path> -v` (no DB; enable tracing per-test via `monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")`).
- This clone has no pre-commit installed; run `uvx ruff check .` before each commit to avoid the CI `qa / pre-commit` failing on lint (e.g. RUF012).

## Verified facts (current code)

- `ZODB.Connection.getTransferCounts(clear=False)` → `(load_count, store_count)`; `clear=False` peeks.
- `metrics/providers/zodb.py` reaches the DB via `context._p_jar`; its monitor resets on close only.
- `pubevents.py`: `_SPAN_KEY = "plone.observability.otel.publish_span"`; `on_pub_start` stores the span on `request.environ[_SPAN_KEY]` (only on the non-excluded path); `_finish(request, error=None)` pops it, sets attrs, and `span.end()`s. `on_after_traversal` adds `http.route`.
- `subrequest.py`: `_traced_subrequest(wrapped, instance, args, kwargs)` opens `start_as_current_span(_span_name(url), context=_parent_context())`; `_parent_context()` currently calls `getRequest()` itself.
- Tests: `span_exporter` fixture; `tests/test_otel_pubevents.py` `FakeRequest` has `.environ` + `.get()` and drives real `PubStart`/`PubSuccess` events; `get_auth_info()` works in that bare setup.

---

### Task 1: `otel/dbcounts.py` helper

**Files:**
- Create: `src/plone/observability/otel/dbcounts.py`
- Test: `tests/test_otel_dbcounts.py`

**Interfaces:**
- Produces:
  - `read_counts(request) -> tuple[int, int] | None` — `(loads, stores)` peeked from the request's main connection, else `None`.
  - `annotate(span, before, after) -> None` — sets `plone.zodb.objects_loaded`/`plone.zodb.objects_stored` from `after - before`; no-op if any of `span`/`before`/`after` is `None`.
  - `_connection(request)` — main connection or `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_otel_dbcounts.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'plone.observability.otel.dbcounts'`.

- [ ] **Step 3: Write the module**

Create `src/plone/observability/otel/dbcounts.py`:

```python
"""Per-span ZODB transfer-count attributes (objects loaded/stored).

Peeks ``ZODB.Connection.getTransferCounts(False)`` (no reset) at span start/end
and records the delta. The process-wide LoadStoreActivityMonitor resets only on
connection close (after spans end), so peeking here is non-disruptive.
"""

_LOADED_ATTR = "plone.zodb.objects_loaded"
_STORED_ATTR = "plone.zodb.objects_stored"


def _connection(request):
    """The request's main ZODB connection, or None."""
    try:
        return request.PARENTS[-1]._p_jar
    except Exception:
        return None


def read_counts(request):
    """``(loads, stores)`` peeked from the main connection, or None."""
    conn = _connection(request)
    if conn is None:
        return None
    try:
        return conn.getTransferCounts(False)
    except Exception:
        return None


def annotate(span, before, after):
    """Set objects_loaded/stored on ``span`` from the ``after - before`` delta."""
    if span is None or before is None or after is None:
        return
    span.set_attribute(_LOADED_ATTR, after[0] - before[0])
    span.set_attribute(_STORED_ATTR, after[1] - before[1])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check src/plone/observability/otel/dbcounts.py tests/test_otel_dbcounts.py
git add src/plone/observability/otel/dbcounts.py tests/test_otel_dbcounts.py
git commit -m "feat(otel): dbcounts helper for per-span ZODB transfer counts (#49)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(Check the commit's own exit code; if pre-commit elsewhere reformats, re-add and re-commit.)

---

### Task 2: Wire into publish + subrequest spans

**Files:**
- Modify: `src/plone/observability/otel/pubevents.py`
- Modify: `src/plone/observability/otel/subrequest.py`
- Create: `news/49.feature`
- Test: `tests/test_otel_dbcounts.py`

**Interfaces:**
- Consumes: `dbcounts.read_counts`, `dbcounts.annotate` (Task 1).
- Produces: `plone.zodb.objects_loaded`/`objects_stored` on the `ZPublisher.publish` span and on `subrequest` spans.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_otel_dbcounts.py`:

```python
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
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "ZPublisher.publish"
    )
    assert span.attributes["plone.zodb.objects_loaded"] == 42
    assert span.attributes["plone.zodb.objects_stored"] == 3
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py::test_subrequest_span_carries_zodb_counts tests/test_otel_dbcounts.py::test_publish_span_carries_request_total -v`
Expected: FAIL — `KeyError: 'plone.zodb.objects_loaded'` (attribute not set yet).

- [ ] **Step 3: Wire `pubevents.py`**

Add the import (with the other otel imports):

```python
from plone.observability.otel import dbcounts
```

Add the baseline key next to `_SPAN_KEY`:

```python
_ZODB_BASELINE_KEY = "plone.observability.otel.zodb_baseline"
```

In `on_pub_start`, after `event.request.environ[_SPAN_KEY] = span`, stash the baseline:

```python
    event.request.environ[_SPAN_KEY] = span
    event.request.environ[_TOKEN_KEY] = token
    event.request.environ[_ZODB_BASELINE_KEY] = dbcounts.read_counts(event.request)
```

In `_finish`, after the `if span is None: return` guard and before `span.end()`, annotate:

```python
    before = request.environ.pop(_ZODB_BASELINE_KEY, None)
    dbcounts.annotate(span, before, dbcounts.read_counts(request))
    if error is not None:
        span.set_status(Status(StatusCode.ERROR))
        span.record_exception(error)
    span.end()
```

(Place the two new lines just before the existing `if error is not None:` block.)

- [ ] **Step 4: Wire `subrequest.py`**

Add the import:

```python
from plone.observability.otel import dbcounts
```

Change `_parent_context` to take the request explicitly:

```python
def _parent_context(request):
    """Context nesting the span under the active transform span, else current."""
    if request is not None:
        try:
            span = request.environ.get(_SINGLE_SPAN_KEY)
        except Exception:
            span = None
        if span is not None:
            return set_span_in_context(span)
    return None  # None -> start_as_current_span uses the current context
```

Update `_traced_subrequest` to resolve the request once, pass it to `_parent_context`, and bracket the call with count peeks:

```python
def _traced_subrequest(wrapped, instance, args, kwargs):
    if not is_enabled() or exclusions.is_suppressed():
        return wrapped(*args, **kwargs)
    url = args[0] if args else kwargs.get("url", "")
    request = getRequest()
    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(
        _span_name(url), context=_parent_context(request)
    ) as span:
        span.set_attribute("http.url", url)
        span.set_attribute("http.method", "GET")
        before = dbcounts.read_counts(request)
        try:
            response = wrapped(*args, **kwargs)
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(exc)
            raise
        dbcounts.annotate(span, before, dbcounts.read_counts(request))
        status = getattr(response, "status", None)
        if isinstance(status, int):
            span.set_attribute("http.status_code", status)
        return response
```

- [ ] **Step 5: Run the dbcounts + touched-span test modules**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py tests/test_otel_subrequest.py tests/test_otel_pubevents.py -v`
Expected: PASS (Task 1 unit tests, the 2 new integration tests, and the existing subrequest/pubevents suites — the `_parent_context(request)` refactor keeps them green because the wrapper still calls `getRequest()`).

- [ ] **Step 6: Create the news fragment**

Create `news/49.feature`:

```
Record objects loaded/stored per span (``plone.zodb.objects_loaded`` / ``plone.zodb.objects_stored``) on the publish span (request total) and each subrequest span (per-tile delta), making N+1 object-load cost visible in traces. ([#49](https://github.com/plone/plone.observability/issues/49))
```

- [ ] **Step 7: Full suite + lint**

Run: `.venv/bin/pytest -q` → expected all pass.
Run: `uvx ruff check .` → expected `All checks passed!`.

- [ ] **Step 8: Commit**

```bash
git add src/plone/observability/otel/pubevents.py src/plone/observability/otel/subrequest.py news/49.feature tests/test_otel_dbcounts.py
git commit -m "feat(otel): annotate publish + subrequest spans with ZODB counts (#49)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(Check the commit's exit code.)

---

## Self-Review

**Spec coverage:**
- `dbcounts.py` (`read_counts`/`annotate`/`_connection`, peek no-reset, defensive) → Task 1. ✓
- Attribute names locked, always both → Task 1 `annotate` + tests. ✓
- Publish span = request total → Task 2 Step 3 (baseline in `on_pub_start`, annotate in `_finish`) + test. ✓
- Subrequest span = per-tile delta → Task 2 Step 4 + test. ✓
- Same connection / delta correctness → covered by the integration tests advancing one fake connection. ✓
- Defensive (no connection → no attrs) → Task 1 `read_counts`/`annotate` no-ops + `test_read_counts_none_without_connection`. ✓
- Scope: only publish + subrequest; process counters untouched → no edits elsewhere. ✓
- News fragment (towncrier `feature`) → Task 2 Step 6. ✓

**Placeholder scan:** none.

**Type consistency:** `read_counts(request) -> (loads, stores)|None`, `annotate(span, before, after)`, `_parent_context(request)`, `_ZODB_BASELINE_KEY` — used consistently across `dbcounts.py`, `pubevents.py`, `subrequest.py`, and the tests. The `_parent_context` signature change is applied at its definition and its single call site.
