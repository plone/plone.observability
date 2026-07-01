# Per-span ZODB load time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `plone.zodb.load_time_ms` to every span that already carries the ZODB object counts, measuring the time spent materialising objects (round-trip + decode).

**Architecture:** Patch `ZODB.Connection.Connection.setstate` (the storage-agnostic load chokepoint) to accumulate elapsed nanoseconds on the connection (`_otel_load_time_ns`), and extend `dbcounts` so `read_counts` returns a 3-tuple `(loads, stores, load_time_ns)` and `annotate` emits `plone.zodb.load_time_ms` from the delta. Every existing call site (pubevents/subrequest/rendering) passes `read_counts` straight to `annotate`, so no call site changes.

**Tech Stack:** ZODB `Connection.setstate`, `time.perf_counter_ns`, OpenTelemetry span attributes, `otel/dbcounts.py`, pytest with the `span_exporter` fixture.

## Global Constraints

- Attribute (locked): `plone.zodb.load_time_ms`, float milliseconds, delta `(after - before)/1_000_000`, rounded to 3 decimals.
- Measure the **whole** `setstate` (round-trip + unpickle/decode) — one patch on `ZODB.Connection.Connection.setstate`, storage-agnostic. Do not touch storage packages.
- The `setstate` wrapper times **unconditionally** (no `is_enabled()`/`is_suppressed()` per call) — it is installed only while tracing is active, and the delta is read only at real spans. Use `try/finally` so time is recorded even when the load raises; never swallow the exception.
- Accumulate on the connection: `self._otel_load_time_ns = getattr(self, "_otel_load_time_ns", 0) + elapsed`. Never reset (deltas are baseline-independent, like the transfer counts).
- `read_counts(request)` returns `(loads, stores, load_time_ns)` or `None`; third element is `getattr(conn, "_otel_load_time_ns", 0)`. `annotate` stays a no-op on `None`.
- Install/uninstall the patch in `otel/zodb.py`'s existing `register()` / `unregister()` (already called from `otel/wsgi.py`). Idempotent.
- Commit footer exactly: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Run tests: `.venv/bin/pytest <path> -v`. Before committing run `uvx pre-commit run --all-files` (CI `qa` = ruff + ruff-format + zpretty; plain `ruff check` is not enough).

## Verified facts (current code)

- `ZODB/Connection.py`: `Connection.setstate(self, obj)` does `p, serial = self._storage.load(oid)` then `self._load_count += 1` then `self._reader.setGhostState(obj, p)`. Only `setstate` increments `_load_count` (the counter behind `plone.zodb.objects_loaded`). `_storage` is an MVCC adapter → works for every backend.
- `otel/dbcounts.py`: `read_counts(request)` returns `conn.getTransferCounts(False)` (a `(loads, stores)` tuple) or `None`; `annotate(span, before, after)` sets `plone.zodb.objects_loaded`/`_stored` from the delta, no-op on `None`.
- `otel/zodb.py`: module-level `import` block ends at `from plone.observability.otel.provider import TRACER_NAME`; `register()` registers a `CommitTracer` transaction synchronizer guarded by `_synch`; `unregister()` unregisters it.
- Tests: `tests/test_otel_dbcounts.py` has a `_Conn` fake (`getTransferCounts`) and asserts `read_counts(_Req(conn)) == (5, 2)` and `annotate(span, (1, 1), (4, 1))`. `tests/test_otel_zodb.py` uses a `register()`/`unregister()` fixture + `span_exporter`.

---

### Task 1: `dbcounts` carries load time (3-tuple + `load_time_ms`)

**Files:**
- Modify: `src/plone/observability/otel/dbcounts.py`
- Test: `tests/test_otel_dbcounts.py`

**Interfaces:**
- Produces: `read_counts(request) -> (loads, stores, load_time_ns) | None`; `annotate` also sets `plone.zodb.load_time_ms`.

- [ ] **Step 1: Update the failing tests**

In `tests/test_otel_dbcounts.py`, extend the `_Conn` fake to carry a load-time accumulator and update the affected assertions.

Change the `_Conn` class:

```python
class _Conn:
    def __init__(self, loads=0, stores=0, load_time_ns=0):
        self.loads = loads
        self.stores = stores
        self._otel_load_time_ns = load_time_ns

    def getTransferCounts(self, clear=False):
        return (self.loads, self.stores)
```

Update `test_read_counts_peeks_without_reset` to expect the 3-tuple:

```python
def test_read_counts_peeks_without_reset():
    from plone.observability.otel import dbcounts

    conn = _Conn(loads=5, stores=2, load_time_ns=9)
    assert dbcounts.read_counts(_Req(conn)) == (5, 2, 9)
    assert conn.getTransferCounts(False) == (5, 2)  # peek, never reset
```

Update `test_annotate_sets_delta_including_zero` to 3-tuples and assert the new attribute:

```python
def test_annotate_sets_delta_including_zero():
    from plone.observability.otel import dbcounts

    span = _Span()
    dbcounts.annotate(span, (1, 1, 1_000_000), (4, 1, 6_000_000))
    assert span.attrs["plone.zodb.objects_loaded"] == 3
    assert span.attrs["plone.zodb.objects_stored"] == 0
    assert span.attrs["plone.zodb.load_time_ms"] == 5.0
```

Add a subrequest integration test asserting the span carries the load time (place it after the existing `test_subrequest_span_carries_zodb_counts`):

```python
def test_subrequest_span_carries_load_time(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import subrequest as sr

    conn = _Conn()
    req = _Req(conn)
    req.environ = {}
    monkeypatch.setattr(sr, "getRequest", lambda: req)

    def fake(url, **kw):
        conn._otel_load_time_ns += 3_000_000  # 3 ms of object loads
        return _Resp(200)

    sr._traced_subrequest(fake, None, ("/p/@@tile",), {})

    span = next(
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "subrequest @@tile"
    )
    assert span.attributes["plone.zodb.load_time_ms"] == 3.0
```

(`test_read_counts_none_without_connection` and `test_annotate_noop_on_none` stay unchanged — `None` handling is unaffected.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py -q`
Expected: FAIL — `read_counts` returns a 2-tuple (`(5, 2) != (5, 2, 9)`) and `annotate` raises `IndexError` on `after[2]` / lacks `plone.zodb.load_time_ms`.

- [ ] **Step 3: Update `dbcounts.py`**

In `src/plone/observability/otel/dbcounts.py`, add the attribute constant, extend `read_counts` and `annotate`:

```python
_LOADED_ATTR = "plone.zodb.objects_loaded"
_STORED_ATTR = "plone.zodb.objects_stored"
_LOAD_TIME_ATTR = "plone.zodb.load_time_ms"
```

```python
def read_counts(request):
    """``(loads, stores, load_time_ns)`` peeked from the main connection, or None."""
    conn = _connection(request)
    if conn is None:
        return None
    try:
        loads, stores = conn.getTransferCounts(False)
    except Exception:
        return None
    return (loads, stores, getattr(conn, "_otel_load_time_ns", 0))


def annotate(span, before, after):
    """Set objects_loaded/stored + load_time_ms on ``span`` from the delta."""
    if span is None or before is None or after is None:
        return
    span.set_attribute(_LOADED_ATTR, after[0] - before[0])
    span.set_attribute(_STORED_ATTR, after[1] - before[1])
    span.set_attribute(_LOAD_TIME_ATTR, round((after[2] - before[2]) / 1_000_000, 3))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_dbcounts.py -v`
Expected: PASS (existing + the new `test_subrequest_span_carries_load_time`).

- [ ] **Step 5: Lint + commit**

```bash
uvx pre-commit run --files src/plone/observability/otel/dbcounts.py tests/test_otel_dbcounts.py
git add src/plone/observability/otel/dbcounts.py tests/test_otel_dbcounts.py
git commit -m "feat(otel): carry ZODB load time in dbcounts (plone.zodb.load_time_ms)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(Check the commit's own exit code.)

---

### Task 2: Time `setstate` in `otel/zodb.py`

**Files:**
- Modify: `src/plone/observability/otel/zodb.py`
- Create: `news/+zodb-load-time.feature`
- Test: `tests/test_otel_zodb.py`

**Interfaces:**
- Consumes: nothing from Task 1 at runtime (independent); together they light up `load_time_ms` end to end.
- Produces: `Connection.setstate` accumulates `_otel_load_time_ns` on the connection while `zodb` is registered.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_otel_zodb.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_otel_zodb.py::test_traced_setstate_accumulates_and_passes_through tests/test_otel_zodb.py::test_register_patches_and_unregister_restores_setstate -v`
Expected: FAIL — `zodb` has no `_traced_setstate`; `register()` does not patch `Connection.setstate`.

- [ ] **Step 3: Add the `setstate` patch to `zodb.py`**

In `src/plone/observability/otel/zodb.py`, add `import time` to the import block:

```python
from opentelemetry import trace
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME

import time
```

Add the wrapper + patch/unpatch helpers (near the bottom, before `register`):

```python
_setstate_patched = []


def _traced_setstate(original):
    def setstate(self, obj):
        start = time.perf_counter_ns()
        try:
            return original(self, obj)
        finally:
            self._otel_load_time_ns = (
                getattr(self, "_otel_load_time_ns", 0)
                + time.perf_counter_ns()
                - start
            )

    return setstate


def _patch_setstate():
    from ZODB.Connection import Connection

    original = Connection.setstate
    if getattr(original, "_otel_wrapped", False):
        return
    wrapper = _traced_setstate(original)
    wrapper._otel_wrapped = True
    wrapper._otel_original = original
    Connection.setstate = wrapper
    _setstate_patched.append((Connection, original))


def _unpatch_setstate():
    while _setstate_patched:
        cls, original = _setstate_patched.pop()
        cls.setstate = original
```

Extend `register()` and `unregister()` to include the patch:

```python
def register():
    global _synch
    _patch_setstate()
    if _synch is None:
        import transaction

        _synch = CommitTracer()
        transaction.manager.registerSynch(_synch)


def unregister():
    global _synch
    _unpatch_setstate()
    if _synch is not None:
        import transaction

        transaction.manager.unregisterSynch(_synch)
        _synch = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_otel_zodb.py -v`
Expected: PASS (existing commit-tracer tests + the three new ones).

- [ ] **Step 5: Create the news fragment**

Create `news/+zodb-load-time.feature`:

```
Add ``plone.zodb.load_time_ms`` to every span that already carries the ZODB object counts (publish, subrequest, viewlet/portlet render): the time spent materialising objects (round-trip + decode), so per-tile/per-request object-load cost is visible in traces.
```

- [ ] **Step 6: Full suite + lint**

Run: `.venv/bin/pytest -q` → expected all pass.
Run: `uvx pre-commit run --all-files` → expected all hooks pass.

- [ ] **Step 7: Commit**

```bash
git add src/plone/observability/otel/zodb.py news/+zodb-load-time.feature tests/test_otel_zodb.py
git commit -m "feat(otel): time ZODB setstate to populate per-span load time

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `plone.zodb.load_time_ms` float ms, delta/1e6 rounded → Task 1 `annotate` + `_LOAD_TIME_ATTR` + test. ✓
- Whole-`setstate` timing, storage-agnostic single patch → Task 2 `_traced_setstate` + `_patch_setstate`. ✓
- Unconditional timing, `try/finally`, never swallow → Task 2 wrapper + `test_traced_setstate_records_time_on_exception`. ✓
- Accumulate on connection, never reset → Task 2 wrapper (`getattr(..., 0) + elapsed`). ✓
- `read_counts` 3-tuple, `getattr` default 0, `annotate` no-op on None → Task 1 + tests. ✓
- Install/uninstall in existing `register()`/`unregister()`, idempotent → Task 2 Step 3 + restore test. ✓
- No call-site changes (pubevents/subrequest/rendering) → confirmed: they pass `read_counts` straight to `annotate`; their fake connections lack `_otel_load_time_ns` so `read_counts` returns `…, 0` and their existing assertions are unaffected. ✓
- News fragment → Task 2 Step 5. ✓

**Placeholder scan:** none.

**Type consistency:** `read_counts -> (loads, stores, load_time_ns)|None`, `annotate(span, before, after)` reading `[0]/[1]/[2]`, `_traced_setstate(original)`, `_patch_setstate()`/`_unpatch_setstate()`, `_otel_load_time_ns`, `_LOAD_TIME_ATTR = "plone.zodb.load_time_ms"` — consistent across both tasks and tests.
