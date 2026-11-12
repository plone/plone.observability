# About metrics and cardinality

The metrics endpoint is small on the surface and opinionated underneath.
This page explains the choices that shape what it measures and how.
It covers label cardinality, metric scope, the cache in front of the expensive metrics, the memory metrics, and the two ZODB monitors.

## Why user identity is never a label

Prometheus stores one time series per unique combination of label values.
A label whose value is drawn from an unbounded set—a user id, a session id, a full URL with query string—multiplies the series count without bound.
This is the single most common way to make a Prometheus server fall over, and it is hard to undo once the data is in.

To avoid that, plone.observability keeps labels low-cardinality on purpose.
Request metrics split only by `auth="authenticated"` or `auth="anonymous"`, which is two values, not two million.
User identity, when you want it at all, belongs on a trace span, where each span is a separate record and high cardinality is the norm.
That is why `enduser.id` is a span attribute gated behind `PLONE_OBSERVABILITY_OTEL_USER_ID`, and never a metric label.

## Global versus instance scope

Several Plone instances usually share one ZODB.
That makes some numbers per-process and others shared, and aggregating them the same way gives wrong answers.

A metric tagged `scope="instance"` is local to one process: its request count, its resident memory, its open connections.
To get a fleet total you sum across instances.

A metric tagged `scope="global"` is a property of the shared database: the object count, the content totals.
Every instance reports the same value, so summing across instances multiplies it by the number of instances.
For global metrics you pick one instance to read from instead.

The `scope` label exists so that whoever writes the PromQL can tell the two apart without memorizing which metric is which.

## Why some metrics are cached

Most metrics are cheap: read a counter, read a gauge, done.
A few are not.
The database-wide object count and the database size are full-table operations on a Postgres-backed storage.
The content counts walk the catalog indexes of every Plone site.
Running them on every scrape, every fifteen or thirty seconds, forever, would put a steady, pointless load on the database.

These metrics sit behind a short time-to-live cache instead, sixty seconds by default, tunable with `PLONE_OBSERVABILITY_METRICS_CACHE_TTL`.
The cache lives at module level, keyed by database name or site id, because `@@metrics` builds its providers afresh on every scrape.
The numbers move slowly enough that a minute of staleness is invisible, and the database is spared the repeated full scans.

## Where memory grows

`plone_process_rss_bytes` tells you that a process grows.
It does not tell you where.
Finding out used to mean inspecting the heap of a live process, which is slow and risky.
It was also only possible after someone noticed the growth.
The memory metrics split the resident memory into parts that point at different causes, cheaply enough to collect on every scrape.

`plone_process_rss_anon_bytes` is the memory the process allocated itself.
`plone_process_rss_file_bytes` is the resident part of mapped files, mostly shared libraries.
Growth almost always shows up in the anonymous part.

Inside the anonymous part, Python serves small objects from its own allocator.
`plone_python_allocated_blocks` counts them.
Growth there means more Python objects are alive: a cache that does not evict, or objects pinned by a reference nobody expected.
Larger objects and most C extensions allocate through `malloc`, which `plone_malloc_inuse_bytes` measures.
`plone_malloc_free_bytes` is memory that `malloc` has taken from the system but does not use.
When it grows while the memory in use stays flat, the heap is fragmented.
The process is not leaking.

Two leak detectors watch for specific patterns.
`plone_python_interned_strings` grows when code keeps creating new identifiers, for example a template that is compiled again on every request.
`plone_gc_uncollectable_total` counts reference cycles that the garbage collector cannot free.
`plone_gc_pause_seconds` shows how long collections stop the process, which adds directly to request latency.

### Connections that outlive the pool

The ZODB connection pool keeps a few connections, each with its own object cache.
When the pool has more than it needs, it releases one and forgets it.
Normally nothing else references that connection, and the garbage collector frees it.

If something still references the released connection, it stays in memory.
So does every object it loaded, because each object points back to its connection.
A stored traceback is enough, since its frames hold the objects a request was working on.
The pool no longer counts such a connection.
`plone_zodb_connections` does not show it.

`plone_zodb_connections_alive` counts every connection that is still in memory.
Above `plone_zodb_connections`, it shows released connections that have not been freed.
A short excess after a release is normal.
A connection references itself.
Only the cyclic garbage collector frees it, which can take a while on a large heap.
A leak shows as an excess that persists for hours or keeps growing.

### Why the malloc metrics are opt-in

`mallinfo2()` is the only way to read the glibc allocator's numbers, and it is not cheap.
It walks every free memory chunk while holding the allocator lock.
On a heap fragmented into a million free chunks, a call takes about 100 milliseconds.
Threads that need memory wait for it.
The cost grows with fragmentation, the very condition the metric is meant to show.
The package therefore collects these metrics only when you set `PLONE_OBSERVABILITY_MALLINFO=1`.
It caches them like the other expensive metrics.

They also have a blind spot.
They cover only glibc `malloc`.
A Rust extension may use its own allocator, such as mimalloc.
The anonymous memory that no other metric accounts for is then the part these allocators hold.
A jemalloc loaded with `LD_PRELOAD` replaces `malloc` entirely.
glibc then reports zero for everything, which looks plausible and is wrong.
The package detects jemalloc and leaves the malloc metrics out instead.

## The ZODB activity monitor

`plone_zodb_loads_total` and `plone_zodb_stores_total` count objects loaded from and stored to the database.
They come from a minimal activity monitor that the package installs into the database's activity-monitor slot on the first metrics scrape.
It is storage-agnostic, so it works the same on FileStorage, RelStorage, and zodb-pgjsonb, and it is O(1) in memory.

These two counters are where you catch a "loads per request" regression early: `rate(plone_zodb_loads_total) / rate(plone_requests_total)` rising over time usually means a new view is waking up far more objects than it needs.

The monitor is installed only if no activity monitor is already configured.
A pre-existing monitor is never overridden—the package logs a warning and leaves the two counters unavailable instead.
Set `PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR=0` to skip installation entirely.

## Conflict metrics

`plone_zodb_conflicts_total` counts ZODB `ConflictError`s raised during request publication.

A write conflict means two transactions changed the same object concurrently, which points at a write hotspot.
A read conflict means an object a transaction required to stay current was changed underneath it, which points at long transactions or `readCurrent` invariants.
Both are counted.

The `retry` label separates the two outcomes that matter operationally.
`retry="true"` is a conflict that was retried, which usually recovers and is invisible to the user.
`retry="false"` is the final attempt that gave up and surfaced an error.
Watching the second one tells you when contention is actually hurting users, not just costing a retry.

```{seealso}
- {doc}`/reference/metrics` for the full metric list and the scope label.
- {doc}`/how-to/scrape-with-prometheus` for scrape configuration and PromQL.
```
