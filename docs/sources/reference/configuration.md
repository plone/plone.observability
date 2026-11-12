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

`PLONE_OBSERVABILITY_READINESS_CACHE_TTL`
:   Seconds to reuse the result of a readiness run, successful or not, for `/ready` and `/startup`.
    A burst of probes then costs one run.
    Set to `0` to run the checks on every probe, unless a run is already in progress.
    Default: `2`.

`PLONE_OBSERVABILITY_READINESS_STUCK_AFTER`
:   Seconds after which a readiness run that has not returned counts as stuck.
    Until then, probes that arrive during the run get the last result.
    After that they get `503` with a `message`, and a warning is logged once.
    Default: `10`.

## Metrics

`PLONE_OBSERVABILITY_METRICS_ALLOWLIST`
:   Comma-separated CIDRs allowed to access `@@metrics`.
    Default: empty, which allows all IP addresses.

`PLONE_OBSERVABILITY_TRUSTED_PROXIES`
:   Comma-separated CIDRs of trusted reverse proxies, used to resolve the client address from `X-Forwarded-For`.
    Default: `127.0.0.1,::1`.

`PLONE_OBSERVABILITY_METRICS_CACHE_TTL`
:   Seconds to cache the expensive-to-collect metrics: the content catalog counts, the database-wide ZODB gauges (`plone_zodb_object_count`, `plone_zodb_db_size_bytes`), and the `plone_malloc_*` metrics.
    Default: `60`.

`PLONE_OBSERVABILITY_MALLINFO`
:   Collect the `plone_malloc_*` metrics from glibc's `mallinfo2()`.
    The call holds the allocator lock while it walks every free memory chunk.
    On a heap fragmented into a million free chunks, it takes about 100 milliseconds.
    Threads that allocate memory wait meanwhile.
    When jemalloc replaces `malloc`, this setting has no effect, and the `plone_jemalloc_*` metrics are reported without it.
    Set to `1` to enable.
    Default: `0`.

`PLONE_OBSERVABILITY_REQUEST_RSS`
:   Read the resident set size before and after each request and each tile subrequest.
    Enables the `plone_request_rss_growth_bytes` histogram, the warning below, and the `plone.process.rss_*` span attributes.
    It needs `/proc/self/statm` (Linux).
    Set to `1` to enable.
    Default: `0`.

`PLONE_OBSERVABILITY_REQUEST_RSS_WARN_MIB`
:   RSS growth of a single request, in MiB, that logs a warning with the request method and path.
    The query string is left out.
    Set to `0` to disable the warning.
    Applies only when `PLONE_OBSERVABILITY_REQUEST_RSS` is enabled.
    Default: `20`.

`PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR`
:   Install a minimal ZODB activity monitor for the load and store counters.
    Set to `0` to disable.
    Default: `1`.

## OpenTelemetry tracing

These variables apply only when the `opentelemetry` extra is installed.
The standard `OTEL_*` variables are honored directly.
The list below names them for convenience, alongside the package-specific overrides.

`OTEL_EXPORTER_OTLP_ENDPOINT`
:   OTLP collector endpoint.
    Setting it enables tracing.

`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
:   OTLP collector endpoint for spans only.
    Setting it enables tracing.

`OTEL_EXPORTER_OTLP_PROTOCOL`
:   Transport for the OTLP exporter: `grpc` or `http/protobuf`.
    `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` takes precedence for spans.
    Any other value logs a warning once and falls back to `grpc`.
    Default: `grpc`.

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

`PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS`
:   Enable the optional external-I/O instrumentors (botocore, requests, urllib3, httpx, psycopg).
    Each activates only when both the instrumentation package (`opentelemetry-io` / `opentelemetry-db` extras) and the instrumented library are installed.
    Accepts `1` or `0`.
    Default: `0`.

`PLONE_OBSERVABILITY_OTEL_RENDER`
:   Emit the render spans for viewlet managers, viewlets, portlet columns, and portlets.
    Accepts `1` or `0`.
    Default: `1`.

`PLONE_OBSERVABILITY_OTEL_USER_ID`
:   Include `enduser.id` on spans.
    This is personally identifiable information.
    It is off by default.

```{seealso}
{doc}`/explanation/health-probes` explains why the health server runs on a separate port, and {doc}`/how-to/install` shows how to wire the WSGI filters that activate metrics and tracing.
```
