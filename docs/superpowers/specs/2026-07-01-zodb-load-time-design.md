# Per-span ZODB load time

**Date:** 2026-07-01
**Status:** Approved (design)

## Summary

Extend the per-span ZODB attribution (b14) with the **time** spent materialising objects, not
just the count. Every span that already carries `plone.zodb.objects_loaded` gains
`plone.zodb.load_time_ms` — so a slow tile shows *"312 object loads / 480 ms"*, directly
exposing where object-load round-trips (the dominant cost of listing tiles on Postgres-backed
storage) go. No per-object spans (that would explode); the aggregate load time lands on the
spans that already exist.

## Mechanism (verified, storage-agnostic)

`ZODB.Connection.Connection.setstate` is the single, storage-independent chokepoint for object
loads (`ZODB/Connection.py`):

```python
p, serial = self._storage.load(oid)     # the storage round-trip
self._load_count += 1                     # the counter behind plone.zodb.objects_loaded
self._reader.setGhostState(obj, p)        # unpickle / decode
```

Only line 786 increments `_load_count`, so timing `setstate` covers exactly the loads we
already count. `self._storage` is an MVCC adapter, so this works for every backend
(zodb-pgjsonb, RelStorage, FileStorage) — no other package is touched.

`load_time_ms` therefore measures **materialisation** = round-trip + unpickle/decode. On
round-trip storage the round-trip dominates; isolating pure I/O would require storage-specific
patching and is intentionally out of scope.

## Components

### `otel/zodb.py` — time `setstate`

Add a monkeypatch (alongside the existing `CommitTracer` synchronizer) installed by
`register()` and reverted by `unregister()`:

- `_traced_setstate(original)` wraps `Connection.setstate(self, obj)` in
  `time.perf_counter_ns()` with `try/finally` and accumulates the elapsed nanoseconds on the
  **connection**: `self._otel_load_time_ns = getattr(self, "_otel_load_time_ns", 0) + elapsed`
  (parallel to ZODB's own `_load_count`).
- Patch `ZODB.Connection.Connection.setstate`; track it for restore; idempotent.

**Deliberate perf choice:** the wrapper times **unconditionally** — no `is_enabled()` /
`is_suppressed()` per call (unlike `otel/catalog.py`). `setstate` runs thousands of times per
request, so a per-call env check would be measurable; the patch is only *installed* while
tracing is active, and the delta is *read* only at real spans (excluded/suppressed requests
simply never read it). Cost per load: two `perf_counter_ns()` calls plus an add (~tens of ns).

### `otel/dbcounts.py` — carry the time into the delta

- `read_counts(request)` now returns a **3-tuple** `(loads, stores, load_time_ns)` (or `None`
  when there is no connection); the third element is `getattr(conn, "_otel_load_time_ns", 0)`.
- `annotate(span, before, after)` additionally sets
  `plone.zodb.load_time_ms = (after[2] - before[2]) / 1_000_000` (float ms), rounded to a
  sensible precision (e.g. 3 decimals).

Every existing call site (`pubevents.py`, `subrequest.py`, `rendering.py`) passes the
`read_counts` result straight to `annotate`, so they need **no change** — the extra tuple
element flows through and the new attribute appears on all their spans automatically.

## Data flow

```
Connection.setstate (patched): perf_counter_ns around storage.load+decode
    -> self._otel_load_time_ns += elapsed          (per connection, monotonic)

span start: before = read_counts(request)          # (loads, stores, load_time_ns)
   ... work (viewlet/portlet/subrequest/whole request) ...
span end:   annotate(span, before, read_counts(request))
   -> plone.zodb.objects_loaded = Δloads
   -> plone.zodb.objects_stored = Δstores
   -> plone.zodb.load_time_ms   = Δload_time_ns / 1e6
```

## Correctness

The accumulator is per-connection and monotonic (never reset — irrelevant, deltas are
baseline-independent, exactly like the transfer counts). Subrequests share the parent
connection, so a start→end delta is that subrequest's load time. The timed set equals the
counted set (both keyed on `setstate`). `try/finally` records time even when a load raises and
never alters load behaviour.

## Error handling

`read_counts` stays fully defensive (`getattr` default `0`, no-op on missing connection);
`annotate` no-ops on `None`. The `setstate` wrapper never swallows the original exception (it
only records time in `finally`).

## Testing

`tests/test_otel_dbcounts.py` (update + add):
1. `read_counts` returns `(loads, stores, load_time_ns)` — fake connection exposing
   `getTransferCounts(False)` and a `_otel_load_time_ns` attribute; update the existing
   2-tuple assertions to 3-tuples.
2. `annotate` sets `plone.zodb.load_time_ms` from the delta (e.g. before `(…, 0)`, after
   `(…, 5_000_000)` → `5.0`); still no-ops on `None`.

`tests/test_otel_zodb.py` (add):
3. `_traced_setstate` accumulates: monkeypatch `time.perf_counter_ns` to a controllable
   counter, call the wrapped `setstate` on a fake connection with a fake `original` (that also
   bumps a fake `_load_count`), assert `conn._otel_load_time_ns` increased by the elapsed
   delta and the original's return value is passed through; a raising `original` still records
   time and re-raises.
4. `register()`/`unregister()` patch and restore `ZODB.Connection.Connection.setstate`
   (idempotent; restored to the original).

`tests/test_otel_dbcounts.py` integration: extend one span test so the fake connection's
`_otel_load_time_ns` advances across the wrapped call and assert the span carries
`plone.zodb.load_time_ms`.

## CHANGES

Towncrier `feature` fragment:

> Add ``plone.zodb.load_time_ms`` to every span that already carries the ZODB object counts
> (publish, subrequest, viewlet/portlet render): the time spent materialising objects
> (round-trip + decode), so per-tile/per-request object-load cost is visible in traces.
