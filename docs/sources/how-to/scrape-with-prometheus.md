# How to scrape and query metrics with Prometheus

This guide shows you how to scrape the `@@metrics` endpoint with Prometheus and query the result with PromQL.

It assumes the `observability` filter is wired.
See {doc}`/how-to/install`.

## Add a scrape job

Point Prometheus at the main Zope port with the `@@metrics` path.

```yaml
scrape_configs:
  - job_name: plone
    static_configs:
      - targets: ["plone-host:8080"]
    metrics_path: /@@metrics
```

If you restrict access with `PLONE_OBSERVABILITY_METRICS_ALLOWLIST`, add the Prometheus server's CIDR to the allowlist.
See {doc}`/reference/configuration`.

## Query the metrics

Total requests across all instances:

```promql
sum(plone_requests_total{job="plone"})
```

Request rate per instance over a five-minute window:

```promql
rate(plone_requests_total{job="plone"}[5m])
```

Approximate median request duration from the histogram:

```promql
histogram_quantile(0.5,
  sum(rate(plone_request_duration_seconds_bucket[5m])) by (le, instance)
)
```

Memory per instance in megabytes:

```promql
plone_process_rss_bytes{job="plone"} / 1024 / 1024
```

## Read global metrics from one instance

Global metrics report the same value on every instance that shares the ZODB.
Summing them double-counts.
Query a single instance instead:

```promql
plone_zodb_object_count{instance="plone-0:8080", scope="global"}
```

## Watch ZODB contention

Overall conflict rate:

```promql
rate(plone_zodb_conflicts_total[5m])
```

Conflicts that gave up after the final retry—the ones users actually felt:

```promql
rate(plone_zodb_conflicts_total{retry="false"}[5m])
```

A loads-per-request smell test that catches views waking up too many objects:

```promql
rate(plone_zodb_loads_total[5m]) / rate(plone_requests_total[5m])
```

```{seealso}
- {doc}`/reference/metrics` for the full metric list and the scope label.
- {doc}`/explanation/metrics-design` for what global versus instance scope means and why the conflict and load counters exist.
```
