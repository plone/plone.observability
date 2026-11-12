# Metrics

The `@@metrics` endpoint is a browser view registered on the application root (`OFS.interfaces.IApplication`).
It collects metrics from all registered `IMetricProvider` adapters and serializes them with an `IMetricFormatter` utility.

Request metrics require the `observability` WSGI filter in your pipeline.
See {doc}`/how-to/install`.

## Endpoint

```text
http://your-plone-host/@@metrics
http://your-plone-host/@@metrics?format=json
```

The default format is Prometheus text.
Pass `?format=json` or send an `Accept: application/json` header to get JSON.

## Built-in metrics

| Metric | Type | Scope | Description |
|---|---|---|---|
| `plone_uptime_seconds` | gauge | instance | Process uptime |
| `plone_info` | info | instance | Python, Zope, and Plone version labels |
| `plone_threads_active` | gauge | instance | Active Python threads |
| `plone_process_rss_bytes` | gauge | instance | Current resident set size, from `/proc/self/statm` (Linux only) |
| `plone_process_rss_peak_bytes` | gauge | instance | Peak resident set size since process start |
| `plone_process_rss_anon_bytes` | gauge | instance | Resident anonymous memory, such as the heap and thread stacks, from `/proc/self/status` (Linux only) |
| `plone_process_rss_file_bytes` | gauge | instance | Resident memory of mapped files, such as shared libraries, from `/proc/self/status` (Linux only) |
| `plone_process_cpu_seconds` | counter | instance | Total CPU time (user + system) |
| `plone_python_allocated_blocks` | gauge | instance | Memory blocks in use by the Python object allocator (pymalloc) |
| `plone_python_interned_strings` | gauge | instance | Number of interned strings (Python 3.12 and later) |
| `plone_gc_collections_total` | counter | instance | Garbage collections, by `generation` |
| `plone_gc_collected_total` | counter | instance | Objects collected by the garbage collector, by `generation` |
| `plone_gc_uncollectable_total` | counter | instance | Uncollectable objects found by the garbage collector, by `generation` |
| `plone_gc_pause_seconds_bucket` | counter | instance | Garbage collection pause histogram buckets, with `_sum` and `_count` |
| `plone_malloc_inuse_bytes` | gauge | instance | Bytes in use through glibc `malloc` (opt-in) |
| `plone_malloc_free_bytes` | gauge | instance | Bytes glibc `malloc` holds but does not use (opt-in) |
| `plone_malloc_mmap_bytes` | gauge | instance | Bytes in large memory-mapped `malloc` allocations (opt-in) |
| `plone_malloc_arena_bytes` | gauge | instance | Bytes of the glibc `malloc` arenas (opt-in) |
| `plone_requests_total` | counter | instance | Total HTTP requests served |
| `plone_request_duration_seconds_sum` | counter | instance | Cumulative request duration |
| `plone_request_duration_seconds_bucket` | counter | instance | Request duration histogram buckets |
| `plone_request_duration_seconds_max` | gauge | instance | Worst-case request duration since the last scrape |
| `plone_request_errors` | counter | instance | HTTP errors by status code |
| `plone_request_rss_growth_bytes_bucket` | counter | instance | Growth of the resident set size per request, histogram buckets with `_sum` and `_count` (opt-in) |
| `plone_zodb_object_count` | gauge | global | Total objects in ZODB |
| `plone_zodb_db_size_bytes` | gauge | global | ZODB file size |
| `plone_zodb_connections` | gauge | instance | Open ZODB connections, in use or idle in the pool |
| `plone_zodb_connections_idle` | gauge | instance | Idle ZODB connections waiting in the pool |
| `plone_zodb_connections_alive` | gauge | instance | ZODB connections still in memory, including ones the pool has released, per database |
| `plone_zodb_pool_size` | gauge | instance | Configured ZODB connection pool size (`pool-size` setting) |
| `plone_zodb_cache_size` | gauge | instance | Objects in the ZODB object cache |
| `plone_zodb_cache_size_bytes` | gauge | instance | Estimated size of the ZODB object caches in bytes, summed over all connections |
| `plone_zodb_loads_total` | counter | instance | Cumulative objects loaded from storage |
| `plone_zodb_stores_total` | counter | instance | Cumulative objects stored to storage |
| `plone_zodb_conflicts_total` | counter | instance | ZODB conflict errors during publish, by `retry` outcome |
| `plone_content_total` | gauge | global | Content objects by portal type and site |
| `plone_content_by_state` | gauge | global | Content objects by workflow state and site |

## Labels

All `plone_request*` metrics carry an `auth="authenticated"` or `auth="anonymous"` label, so traffic can be split by authentication state.
User identity is never a metric label.
It appears only as a span attribute; see {doc}`/reference/configuration` for the `PLONE_OBSERVABILITY_OTEL_USER_ID` setting and {doc}`/explanation/metrics-design` for the reasoning.

`plone_zodb_conflicts_total` carries `retry="true"` for a conflict that was retried and `retry="false"` for the final attempt that gave up.

## Scope

Every metric carries a `scope` label with value `global` or `instance`.

global
:   The value is the same across all Plone instances sharing the same ZODB, for example object count and content totals.
    When aggregating in Prometheus, filter to a single instance to avoid double-counting.

instance
:   The value is specific to this process, for example request counts and resident set size.
    Sum across instances when aggregating.

## The request duration maximum

`plone_request_duration_seconds_max` is a per-scrape-window gauge.
A histogram can only bound latency to its bucket edges, so the true worst-case request time is tracked directly and reset on every scrape.
Scrape it from a single Prometheus target: multiple concurrent scrapers would each see only part of the window.

## Memory metrics

The memory metrics come from the `system` and `python` providers.
Each metric is left out where its source is not available.

`plone_process_rss_anon_bytes` and `plone_process_rss_file_bytes`
:   Read from the `RssAnon` and `RssFile` fields of `/proc/self/status`.
    They require Linux 4.5 or later.

`plone_python_allocated_blocks`
:   Read from `sys.getallocatedblocks()`.
    The value is a number of blocks.
    It does not convert them to bytes.

`plone_python_interned_strings`
:   Read from `sys.getunicodeinternedsize()`, which exists in Python 3.12 and later.
    On Python 3.12, interned strings are never freed.
    The value never decreases there.
    From Python 3.13, it can decrease.

`plone_gc_*_total`
:   Read from `gc.get_stats()`.
    The `generation` label is `0`, `1`, or `2`.
    What a generation holds depends on the Python version.

`plone_gc_pause_seconds`
:   Timed by a `gc.callbacks` hook that the package installs on the first metrics scrape.
    Pauses before the first scrape are not counted.
    Bucket bounds range from 100 microseconds to 1 second.

`plone_malloc_*`
:   Read from glibc's `mallinfo2()`, which exists in glibc 2.33 and later.
    They are off by default.
    Set `PLONE_OBSERVABILITY_MALLINFO=1` to turn them on.
    The values are cached for `PLONE_OBSERVABILITY_METRICS_CACHE_TTL` seconds.
    They cover only memory allocated through glibc `malloc`.
    Memory from other allocators, such as mimalloc in a Rust extension, does not appear in them.
    When a jemalloc loaded with `LD_PRELOAD` replaces `malloc`, the metrics are left out, and a warning is logged once.

## RSS growth per request

`plone_request_rss_growth_bytes` is a histogram of how much the resident set size grew during a request.
It is off by default.
Set `PLONE_OBSERVABILITY_REQUEST_RSS=1` to turn it on.

The `observability` WSGI filter reads `/proc/self/statm` before the request and again when the application returns.
A response body that is streamed after that is not included.
A request during which the resident set size shrank counts as zero growth.
Bucket bounds range from 0 to 256 MiB.

A request that grows the resident set size by more than `PLONE_OBSERVABILITY_REQUEST_RSS_WARN_MIB` logs a warning with its method and path.

## Connections still in memory

`plone_zodb_connections_alive` counts every ZODB connection that a database created and that is still in memory.
It carries a `database` label and is reported for the main database and every database mounted with it.
`plone_zodb_connections` covers only the main database's pool.

The package wraps the database's connection class when Zope opens the database (`IDatabaseOpenedWithRoot`).
A configured `connection-class` stays in effect.
Connections that exist at that moment are counted from the pool.
If the event did not reach the package, the first metrics scrape installs the tracking instead.

The count includes historical connections, which `plone_zodb_connections` does not.
A connection the pool has released stays counted until the garbage collector frees it.
That takes two collections of the oldest generation.

## Catalog backends

`plone_content_total` and `plone_content_by_state` come from the `content` provider, which reads the `portal_type` and `review_state` indexes through the ZCatalog index API, one Plone site at a time.

A catalog backend that keeps its data outside the site cannot rely on that.
If it emulates the index API, the generic provider still emits, but the counts may cover more than one site.
plone-pgcatalog is such a backend: one PostgreSQL table holds all sites, so the generic provider would report the database-wide counts under every site's label.
Such a backend replaces the `content` adapter with its own provider in `overrides.zcml`, keeping the metric names, and plone-pgcatalog does exactly that.
See {doc}`/how-to/add-custom-metric-provider` for how to replace a built-in provider.

```{seealso}
{doc}`/how-to/scrape-with-prometheus` shows scrape configuration and PromQL recipes.
{doc}`/explanation/metrics-design` explains scope, label cardinality, and the ZODB activity and conflict monitors.
```
