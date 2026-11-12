# How to enable OpenTelemetry tracing

This guide shows you how to turn on distributed tracing and send spans to an OTLP collector.

## Install the extra

```shell
pip install "plone.observability[opentelemetry]"
```

## Point it at a collector

Tracing activates when an OTLP endpoint is configured.
Set the standard OpenTelemetry environment variables:

```shell
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
export OTEL_SERVICE_NAME=plone-backend
```

The exporter speaks OTLP over gRPC by default, usually on port `4317`.
If your collector accepts only OTLP over HTTP, usually on port `4318`, select that transport:

```shell
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

For the full set of variables and the package-specific overrides, see {doc}`/reference/configuration`.

## Add the WSGI filter

Add the `opentelemetry` filter to your pipeline.
The wiring is the same as for the other filters.
See {doc}`/how-to/install`.

The filter is required.
It sets up the exporter, installs the instrumentation, and opens the root span of each request.
Without it, no spans are exported.

## Exclude noisy paths

The package's own `@@metrics` scrape is excluded from tracing by default, so the periodic scrape does not flood your traces.
To exclude additional paths, set the standard exclusion variable to a comma-separated list of regexes, matched as a substring against the path:

```shell
export OTEL_PYTHON_WSGI_EXCLUDED_URLS="/@@health,/static"
```

Exclusion applies at both layers, the WSGI root span and the event-driven inner spans, so an excluded path produces no spans at all.

To trace the `@@metrics` scrape after all, turn the defaults off:

```shell
export PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS=0
```

## External I/O spans (S3, HTTP, SQL)

By default only this package's own spans are emitted. To also trace external I/O — S3 blob access (botocore/boto3) and outbound HTTP (requests/urllib3/httpx) — install the instrumentor packages and switch them on:

```shell
pip install "plone.observability[opentelemetry,opentelemetry-io]"
export PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS=1
```

Every supported instrumentor whose package is installed — together with the library it instruments — is enabled; those calls then appear as child spans nested under the active request/publish/render span. Note that `requests` uses `urllib3` internally, so with both enabled a single requests call produces a `requests` span *and* a nested `urllib3` span — install only the instrumentor you want if that is noisy.

(sql-spans-psycopg)=

### SQL spans (psycopg)

When the ZODB sits on PostgreSQL via [zodb-pgjsonb](https://bluedynamics.github.io/zodb-pgjsonb/), or anything else in the process talks to PostgreSQL through psycopg 3, the `opentelemetry-db` extra adds per-statement SQL spans under the same switch:

```shell
pip install "plone.observability[opentelemetry,opentelemetry-db]"
export PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS=1
```

Each statement becomes a child span of the current request span, carrying the query as `db.statement`. A busy request can emit dozens of these — that is the point, but budget for the span volume in your collector. Connections opened before the WSGI pipeline is assembled (a storage's initial pool) are not instrumented; connections created afterwards (pool growth, reconnects) are.

```{seealso}
- {doc}`/reference/tracing` for the emitted spans and their attributes.
- {doc}`/how-to/add-custom-spans` to trace your own code.
- {doc}`/explanation/tracing` for why the spans come from Zope events and how tracing relates to metrics.
```
