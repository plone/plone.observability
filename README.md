# plone.observability

Kubernetes-style health probes and pluggable metrics for Plone.

## Features

- Liveness, readiness, and startup probes on a separate HTTP port
- Pluggable metrics endpoint (`@@metrics`) with Prometheus and JSON output
- Extensible via ZCA: custom health checks, metric providers, and formatters

## Installation

Add `plone.observability` to your package dependencies:

```toml
[project]
dependencies = [
    "plone.observability",
]
```

Then include it in your ZCML:

```xml
<include package="plone.observability" />
```

The package registers itself and starts the health server automatically when Zope starts via a `IProcessStarting` subscriber.

## Configuration

All configuration is done via environment variables.

| Variable | Default | Description |
|---|---|---|
| `PLONE_OBSERVABILITY_HEALTH_HOST` | `0.0.0.0` | Bind address for the health probe server |
| `PLONE_OBSERVABILITY_HEALTH_PORT` | `8081` | Port for the health probe server. Set to `0` to disable. |
| `PLONE_OBSERVABILITY_METRICS_ALLOWLIST` | *(empty, open)* | Comma-separated CIDRs allowed to access `@@metrics`. Empty means all IPs are allowed. |
| `PLONE_OBSERVABILITY_TRUSTED_PROXIES` | `127.0.0.1,::1` | Comma-separated CIDRs of trusted reverse proxies for `X-Forwarded-For` resolution. |
| `PLONE_OBSERVABILITY_METRICS_CACHE_TTL` | `60` | Seconds to cache content catalog metrics (expensive to collect). |

## Health Probes

The health server runs on a dedicated port (default `8081`) in a background daemon thread, separate from the Zope WSGI server. This means it answers even when all Zope threads are busy.

The health server is started by the `egg:plone.observability#healthserver` WSGI filter — add it to your pipeline (see [WSGI filters](#wsgi-middleware-for-request-metrics) below). It is **not** started on Zope process startup, so `zconsole`/script runs never touch the health port.

### Endpoints

| Path | Purpose |
|---|---|
| `/live` | Liveness check — is the process alive? |
| `/ready` | Readiness check — can the process serve requests? |
| `/startup` | Startup check — has the process finished initializing? |

All endpoints return JSON with a 200 on success or 503 on failure:

```json
{
  "status": "ok",
  "checks": {
    "zodb": {"ok": true, "message": "ZODB connection ok"}
  }
}
```

### Kubernetes Integration

```yaml
livenessProbe:
  httpGet:
    path: /live
    port: 8081
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8081
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /startup
    port: 8081
  failureThreshold: 30
  periodSeconds: 10
```

Expose the probe port alongside the main Zope port:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: health
    containerPort: 8081
```

## Metrics

The `@@metrics` endpoint is a browser view registered on the application root (`OFS.interfaces.IApplication`). It collects metrics from all registered `IMetricProvider` adapters and serialises them using an `IMetricFormatter` utility.

### Accessing the endpoint

```
http://your-plone-host/@@metrics
http://your-plone-host/@@metrics?format=json
```

The default format is Prometheus text. Pass `?format=json` or an `Accept: application/json` header to get JSON.

### Built-in metrics

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
| `plone_request_errors` | counter | instance | HTTP errors by status code |
| `plone_zodb_object_count` | gauge | global | Total objects in ZODB |
| `plone_zodb_db_size_bytes` | gauge | global | ZODB file size |
| `plone_zodb_connections` | gauge | instance | Open ZODB connections |
| `plone_zodb_cache_size` | gauge | instance | Objects in the ZODB object cache |
| `plone_zodb_cache_size_bytes` | gauge | instance | ZODB object cache size in bytes |
| `plone_content_total` | gauge | global | Content objects by portal type and site |
| `plone_content_by_state` | gauge | global | Content objects by workflow state and site |

All `plone_request*` metrics additionally carry an `auth="authenticated"|"anonymous"`
label so traffic can be split by authentication state. (User identity is never a
metric label — only a span attribute; see the OpenTelemetry section.)

### Metric scope

Metrics carry a `scope` label with value `"global"` or `"instance"`.

- **global** — the value is the same across all Plone instances sharing the same ZODB (e.g. object count, content totals). When aggregating in Prometheus, avoid double-counting by filtering to a single instance.
- **instance** — the value is specific to this process (e.g. request counts, RSS). Sum across instances when aggregating.

### Prometheus scrape configuration

```yaml
scrape_configs:
  - job_name: plone
    static_configs:
      - targets: ["plone-host:8080"]
    metrics_path: /@@metrics
```

### PromQL examples

Total requests across all instances:

```promql
sum(plone_requests_total{job="plone"})
```

Request rate per instance (5-minute window):

```promql
rate(plone_requests_total{job="plone"}[5m])
```

ZODB object count (global metric — pick one instance to avoid double-counting):

```promql
plone_zodb_object_count{scope="global"} * on(instance) group_left()
  (plone_info{instance=~"plone-0.*"})
```

Or simply query a single instance:

```promql
plone_zodb_object_count{instance="plone-0:8080", scope="global"}
```

Average request duration (p50 approximation from histogram):

```promql
histogram_quantile(0.5,
  sum(rate(plone_request_duration_seconds_bucket[5m])) by (le, instance)
)
```

Memory usage per instance (MB):

```promql
plone_process_rss_bytes{job="plone"} / 1024 / 1024
```

## WSGI Middleware for Request Metrics

The `plone_requests_total` and `plone_request_duration_seconds_*` metrics are populated by the `ObservabilityMiddleware` WSGI middleware. You must add it to your WSGI pipeline to get request metrics. The same applies to the OpenTelemetry root request span (see below) — both are PasteDeploy filters wired the same way.

### Using cookiecutter-zope-instance (recommended)

If your `zope.ini` is generated by
[cookiecutter-zope-instance](https://github.com/plone/cookiecutter-zope-instance)
(3.1.0+), do not edit `zope.ini` by hand — declare the filters via `wsgi_filters`
in your `instance.yaml`:

```yaml
default_context:
    wsgi_filters:
        healthserver:
            use: "egg:plone.observability#healthserver"
        observability:
            use: "egg:plone.observability#observability"
        opentelemetry:
            use: "egg:plone.observability#opentelemetry"
```

This renders the `[filter:*]` sections and wires them into `[pipeline:main]` on
regeneration. Each entry also accepts `options` (extra `key: value` lines) and
`position` (`outer`, the default, or `inner`). See that project's
"Add WSGI middleware to the pipeline" how-to. `healthserver` starts the health
probe server; drop the `opentelemetry` entry if you do not use the tracing extra.

### Using PasteDeploy directly (hand-written zope.ini)

```ini
[pipeline:main]
pipeline =
    healthserver
    egg:plone.observability#observability
    ...
    Zope

[filter:healthserver]
use = egg:plone.observability#healthserver

[filter:observability]
use = egg:plone.observability#observability
```

### Manual WSGI wrapping

```python
from plone.observability.metrics.providers.request import ObservabilityMiddleware

application = ObservabilityMiddleware(application)
```

## OpenTelemetry Tracing (optional)

Install the extra to enable distributed tracing:

```bash
pip install "plone.observability[opentelemetry]"
```

Tracing is **OTel-native**: it honors the standard `OTEL_*` environment
variables and auto-activates when the extra is installed and an OTLP endpoint is
configured. `PLONE_OBSERVABILITY_OTEL_ENABLED` is the master on/off override.

| Variable | Purpose |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint (enables tracing) |
| `OTEL_SERVICE_NAME` | Service name on emitted spans |
| `OTEL_TRACES_SAMPLER` | Sampling strategy |
| `PLONE_OBSERVABILITY_OTEL_ENABLED` | `1`/`0` master override |
| `PLONE_OBSERVABILITY_OTEL_USER_ID` | include `enduser.id` (PII) on spans; default off |

Add the `egg:plone.observability#opentelemetry` filter to your WSGI pipeline for
the root request span — see [WSGI Middleware for Request Metrics](#wsgi-middleware-for-request-metrics)
above (the `wsgi_filters` example wires both filters at once). Without it you
still get the publishing, catalog, and commit spans (registered via ZCML), just
not the outer WSGI/HTTP span.

Emitted spans (depth: request + key Plone internals):

- root request span (WSGI)
- `ZPublisher.publish` — one per request, with `http.route`
- `catalog.searchResults` / `catalog.unrestrictedSearchResults` — per catalog
  query (standard Plone **and** plone-pgcatalog), with `plone.catalog.result_count`
- `transaction.commit` — per ZODB transaction completion

The `ZPublisher.publish` span also carries `enduser.authenticated` (always) and,
when `PLONE_OBSERVABILITY_OTEL_USER_ID` is enabled, `enduser.id`.

Application code can open child spans with the dependency-optional helper (a
no-op when the extra is not installed):

```python
from plone.observability.spans import start_span

with start_span("myapp.expensive_step", {"items": n}):
    do_work()
```

## Extensibility

All components are registered via ZCA and can be extended or replaced by third-party packages.

### Custom liveness check

Implement `ILivenessCheck` and register it as a named utility. Liveness checks MUST NOT access ZODB or block.

```python
from zope.interface import implementer
from plone.observability.interfaces import ILivenessCheck

@implementer(ILivenessCheck)
class MyLivenessCheck:
    name = "myapp"

    def __call__(self):
        # Return (ok: bool, message: str)
        return True, "all good"
```

```xml
<utility
    factory=".checks.MyLivenessCheck"
    provides="plone.observability.interfaces.ILivenessCheck"
    name="myapp"
    />
```

### Custom readiness check

Implement `IReadinessCheck`. Readiness checks may access ZODB.

```python
from zope.interface import implementer
from plone.observability.interfaces import IReadinessCheck

@implementer(IReadinessCheck)
class MyReadinessCheck:
    name = "myapp"

    def __call__(self):
        # Check a dependency
        ok = _check_external_service()
        return ok, "service ok" if ok else "service unavailable"
```

```xml
<utility
    factory=".checks.MyReadinessCheck"
    provides="plone.observability.interfaces.IReadinessCheck"
    name="myapp"
    />
```

### Custom metric provider

Implement `IMetricProvider` as an adapter on `OFS.interfaces.IApplication`.

```python
from zope.interface import implementer
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric

@implementer(IMetricProvider)
class MyMetricProvider:
    name = "myapp"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        yield Metric(
            name="myapp_queue_length",
            value=get_queue_length(),
            type="gauge",
            scope="instance",
            help="Number of items in the processing queue",
        )
```

```xml
<adapter
    factory=".metrics.MyMetricProvider"
    provides="plone.observability.interfaces.IMetricProvider"
    for="OFS.interfaces.IApplication"
    name="myapp"
    />
```

### Custom metric formatter

Implement `IMetricFormatter` as a named utility to support additional wire formats.

```python
from zope.interface import implementer
from plone.observability.interfaces import IMetricFormatter

@implementer(IMetricFormatter)
class CSVFormatter:
    content_type = "text/csv"

    def format(self, metrics):
        lines = ["name,value,type,scope,help"]
        for m in metrics:
            lines.append(f"{m.name},{m.value},{m.type},{m.scope},{m.help}")
        return "\n".join(lines)
```

```xml
<utility
    factory=".formatters.CSVFormatter"
    provides="plone.observability.interfaces.IMetricFormatter"
    name="csv"
    />
```

Access it via `@@metrics?format=csv`.
