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
| `plone_process_rss_bytes` | gauge | instance | Resident set size |
| `plone_process_cpu_seconds` | counter | instance | Total CPU time (user + system) |
| `plone_requests_total` | counter | instance | Total HTTP requests served |
| `plone_request_duration_seconds_sum` | counter | instance | Cumulative request duration |
| `plone_request_duration_seconds_bucket` | counter | instance | Request duration histogram buckets |
| `plone_request_duration_seconds_max` | gauge | instance | Worst-case request duration since the last scrape |
| `plone_request_errors` | counter | instance | HTTP errors by status code |
| `plone_zodb_object_count` | gauge | global | Total objects in ZODB |
| `plone_zodb_db_size_bytes` | gauge | global | ZODB file size |
| `plone_zodb_connections` | gauge | instance | Open ZODB connections |
| `plone_zodb_cache_size` | gauge | instance | Objects in the ZODB object cache |
| `plone_zodb_cache_size_bytes` | gauge | instance | ZODB object cache size in bytes |
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

## Catalog backends

`plone_content_total` and `plone_content_by_state` are produced from the ZCatalog index API and are therefore ZCatalog-only.
On other catalog backends, such as plone-pgcatalog, the generic provider yields nothing, and the backend package ships its own `IMetricProvider` with the same metric names.

```{seealso}
{doc}`/how-to/scrape-with-prometheus` shows scrape configuration and PromQL recipes.
{doc}`/explanation/metrics-design` explains scope, label cardinality, and the ZODB activity and conflict monitors.
```
