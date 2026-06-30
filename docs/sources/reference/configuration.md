# Configuration

All configuration is done through environment variables.
This page is the canonical list.
Every how-to guide links here rather than repeating these values.

## Health server

`PLONE_OBSERVABILITY_HEALTH_HOST`
:   Bind address for the health probe server.
    Default: `0.0.0.0`.

`PLONE_OBSERVABILITY_HEALTH_PORT`
:   Port for the health probe server.
    Default: `8081`.
    Set to `0` to disable the health server.

## Metrics

`PLONE_OBSERVABILITY_METRICS_ALLOWLIST`
:   Comma-separated CIDRs allowed to access `@@metrics`.
    Default: empty, which allows all IP addresses.

`PLONE_OBSERVABILITY_TRUSTED_PROXIES`
:   Comma-separated CIDRs of trusted reverse proxies, used to resolve the client address from `X-Forwarded-For`.
    Default: `127.0.0.1,::1`.

`PLONE_OBSERVABILITY_METRICS_CACHE_TTL`
:   Seconds to cache the expensive-to-collect metrics: the content catalog counts and the database-wide ZODB gauges (`plone_zodb_object_count`, `plone_zodb_db_size_bytes`).
    On Postgres-backed storage those two are full-table queries, so caching keeps `@@metrics` fast.
    Default: `60`.

`PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR`
:   Install a minimal ZODB activity monitor for the load and store counters.
    Set to `0` to disable.
    Default: `1`.

## OpenTelemetry tracing

These variables apply only when the `opentelemetry` extra is installed.
The standard `OTEL_*` variables are honored directly; the table below lists them for convenience alongside the package-specific overrides.

`OTEL_EXPORTER_OTLP_ENDPOINT`
:   OTLP collector endpoint.
    Setting it enables tracing.

`OTEL_SERVICE_NAME`
:   Service name reported on emitted spans.

`OTEL_TRACES_SAMPLER`
:   Sampling strategy.

`OTEL_PYTHON_WSGI_EXCLUDED_URLS`
:   Comma-separated regexes of paths to never trace, matched as a substring search against the path.
    Falls back to `OTEL_PYTHON_EXCLUDED_URLS`.

`PLONE_OBSERVABILITY_OTEL_ENABLED`
:   Master on/off override.
    Accepts `1` or `0`.

`PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS`
:   Default-exclude the package's own `@@metrics` scrape from tracing.
    Accepts `1` or `0`.
    Default: `1`.

`PLONE_OBSERVABILITY_OTEL_USER_ID`
:   Include `enduser.id` on spans.
    This is personally identifiable information; it is off by default.

```{seealso}
{doc}`/explanation/health-probes` explains why the health server runs on a separate port, and {doc}`/how-to/install` shows how to wire the WSGI filters that activate metrics and tracing.
```
