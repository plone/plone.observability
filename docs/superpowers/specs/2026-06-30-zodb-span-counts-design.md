# Per-span ZODB load/store counts

**Date:** 2026-06-30
**Issue:** [#49](https://github.com/plone/plone.observability/issues/49)
**Status:** Approved (design)

## Summary

Record objects loaded/stored **per span** as span attributes, so per-request and
per-tile ZODB round-trip cost (N+1 object loads — the dominant cost of listing tiles on
Postgres-backed storage) is visible directly in the trace. Annotate:

- the root `ZPublisher.publish` span — total objects loaded/stored for the whole request
  (headline number);
- each `plone.subrequest` span — the per-tile delta (breakdown).

Today `plone_zodb_loads_total` (a process-wide counter) cannot be attributed to a request
or span, and the `subrequest @@…` span (b12, #43) is a flat block.

## Attribute names (locked)

- `plone.zodb.objects_loaded`
- `plone.zodb.objects_stored`

Rationale: matches the package's existing span-attribute pattern `plone.<area>.<leaf>`
(`plone.catalog.result_count`, `plone.transform.name`) — `plone`/`zodb` are dot-separated
namespace levels, `objects_loaded` is one multi-word leaf (underscore). Keeps the `plone.`
namespace (every other custom span attr is `plone.*`; avoids colliding with future OTel
`db.*` conventions). Both attributes are **always set**, even when 0.

## Mechanism (verified)

`ZODB.Connection.getTransferCounts(clear=False)` returns `(load_count, store_count)` and,
with `clear=False`, **peeks without resetting**. The existing
`metrics/providers/zodb.py:LoadStoreActivityMonitor` reads `getTransferCounts(True)`
(read+reset) only on connection **close** (request teardown, after all spans end). So
peeking during the request is safe and does not disturb the process-wide counters.

The connection is the request's main-DB connection: `request.PARENTS[-1]._p_jar` (mirrors
how `metrics/providers/zodb.py` reaches the DB via `context._p_jar`). Subrequests run on
the **same** connection/thread (`plone.subrequest` clones the request but reuses the parent
app/connection), so a start→end delta on that connection is exactly the subrequest's load
cost. Counts accumulate during the request; a delta (`after - before`) is independent of
any nonzero baseline.

Multi-database mount points are out of scope: only the main connection's counts are read
(content/tiles live on the main storage). This matches the issue's intent.

## Components

### New `src/plone/observability/otel/dbcounts.py`

- `_connection(request)` → the main ZODB connection (`request.PARENTS[-1]._p_jar`) or
  `None`, fully defensive (no PARENTS / no `_p_jar` → `None`).
- `read_counts(request)` → `(loads, stores)` from `conn.getTransferCounts(False)`, or
  `None` when there is no connection.
- `annotate(span, before, after)` → when `span`, `before` and `after` are all present, set
  `plone.zodb.objects_loaded = after[0] - before[0]` and
  `plone.zodb.objects_stored = after[1] - before[1]` (always both). No-op if any input is
  `None` (e.g. tracing disabled → no span, or no connection).

### `otel/pubevents.py` (publish span = request total)

- `on_pub_start`: after creating the publish span, stash `read_counts(request)` on
  `request.environ` under a new key (`_ZODB_BASELINE_KEY`).
- `_finish`: read `read_counts(request)` again and `annotate(span, baseline, after)` before
  `span.end()`. Pop the baseline key. Guarded by the existing span presence + suppression
  logic.

### `otel/subrequest.py` (per-tile delta)

- In `_traced_subrequest`, inside the `start_as_current_span` block: `before =
  read_counts(getRequest())` before calling `wrapped(...)`; `after = read_counts(...)`
  after; `annotate(span, before, after)`. Reuses the request already resolved for parent
  context.

## Data flow

```
on_pub_start:   baseline = peek(conn)            # stashed on request.environ
  ... main render, transformchain ...
  subrequest span:  before = peek(conn); render tile; after = peek(conn)
                    -> plone.zodb.objects_loaded = after-before   (per tile)
  ...
_finish:        after = peek(conn)
                -> publish span plone.zodb.objects_loaded = after-baseline  (request total)
connection close (later): LoadStoreActivityMonitor reads+resets -> process counters
```

## Error handling

`read_counts` / `_connection` swallow all attribute errors and return `None`; `annotate`
no-ops on `None`. Tracing and request behaviour are never affected. No new dependency.

## Scope (YAGNI)

- Only the `ZPublisher.publish` and `plone.subrequest` spans (as the issue clarified). Not
  transform or commit spans.
- Process-wide counters unchanged.
- Single (main) connection only; multi-DB mounts not attributed.

## Testing

`tests/test_otel_dbcounts.py`:

1. **`read_counts`** with a fake request whose `PARENTS[-1]._p_jar` is a fake connection
   exposing `getTransferCounts(clear)` → returns the peeked tuple; `clear=False` is passed
   (peek). Fake request with no connection → `None`.
2. **`annotate`** sets both attributes from the delta, including a 0 delta; no-ops when
   `before`/`after`/`span` is `None`.
3. **Integration — subrequest span** (`span_exporter`): fake connection on
   `request.PARENTS` returning increasing counts across the wrapped call; assert the
   `subrequest @@…` span carries `plone.zodb.objects_loaded` = the delta.
4. **Integration — publish span** (`span_exporter`): drive `on_pub_start` → (advance fake
   counts) → `on_pub_success`; assert the `ZPublisher.publish` span carries the request
   total.

Mirror the in-memory `span_exporter` fixture and the existing
`test_otel_pubevents.py` / `test_otel_subrequest.py` patterns.

## CHANGES

Towncrier `feature` fragment `news/49.feature`:

> Record objects loaded/stored per span (`plone.zodb.objects_loaded` /
> `plone.zodb.objects_stored`) on the publish span (request total) and each subrequest span
> (per-tile delta), making N+1 object-load cost visible in traces. #49
