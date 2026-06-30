# About metrics and cardinality

The metrics endpoint is small on the surface and opinionated underneath.
This page explains the choices that shape what it measures and how: label cardinality, metric scope, the cache in front of the expensive metrics, and the two ZODB monitors.

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
Two are not.
The database-wide object count and the database size, and the content catalog counts, are full-table operations on a Postgres-backed storage.
Running them on every scrape—every fifteen or thirty seconds, forever—would put a steady, pointless load on the database.

Those two metrics sit behind a short time-to-live cache instead, sixty seconds by default, tunable with `PLONE_OBSERVABILITY_METRICS_CACHE_TTL`.
The numbers move slowly enough that a minute of staleness is invisible, and the database is spared the repeated full scans.

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
