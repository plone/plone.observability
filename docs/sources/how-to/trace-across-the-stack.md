# How to trace one request across the whole stack

This guide shows you how to stitch the ingress, the HTTP cache, the Volto frontend, the Plone backend, and PostgreSQL into a single distributed trace.

The glue is W3C Trace Context: every hop forwards the `traceparent` request header, emits its own spans, and exports them to one shared collector.
A hop that cannot emit spans but forwards the header stays invisible in the trace without breaking it.
The backend needs no propagation setup at all; the WSGI middleware extracts an incoming `traceparent` automatically.

## Prerequisites

- Backend tracing is enabled per {doc}`/how-to/enable-opentelemetry-tracing`.
- Every service can reach one OTLP collector, such as an OpenTelemetry Collector fanning out to Grafana Tempo or Jaeger.

Give each service its own service name (`traefik`, `volto`, `plone-backend`) so the trace view shows who is who.

## Start the trace at the ingress

Traefik 3 ships native OpenTelemetry tracing.
Enable it in the static configuration:

```yaml
tracing:
  serviceName: traefik
  sampleRate: 1.0
  otlp:
    http:
      endpoint: http://otel-collector:4318/v1/traces
```

Traefik opens the entry span for each request and forwards the `traceparent` header downstream.
If you run a different ingress, use its OpenTelemetry support instead: ingress-nginx has an OpenTelemetry module, and Envoy-based ingresses trace natively.

Make the sampling decision here at the edge, with `sampleRate`.
The SDKs further down sample parent-based by default, so they follow the decision of the ingress and you never get partial traces.

## Let Varnish pass the context through

Open-source Varnish emits no spans, but it forwards request headers it does not know, so the trace survives the cache without configuration.
If your VCL scrubs request headers, make sure `traceparent` and `tracestate` survive.

A cache hit is answered without touching the backend, so it produces no downstream spans.
The time spent in Varnish shows up as the gap between the ingress span and the first downstream span.
If you want the hit/miss outcome on the trace, emit an `X-Cache` response header from VCL and record it on the ingress span with Traefik's `tracing.capturedResponseHeaders` option.
If you need real cache spans, Varnish Enterprise ships native OpenTelemetry support.

## Trace the Volto server

The Node SSR process joins the trace through the OpenTelemetry Node auto-instrumentation; Volto itself needs no code changes.
Add the package to your frontend:

```shell
npm install @opentelemetry/auto-instrumentations-node
```

Start the server with the instrumentation preloaded:

```shell
export OTEL_SERVICE_NAME=volto
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export NODE_OPTIONS="--require @opentelemetry/auto-instrumentations-node/register"
```

Incoming SSR requests continue the trace the ingress started, and the API requests Volto makes to the backend carry the `traceparent` onward.

After hydration the browser calls `++api++` directly, so those requests start their trace at the ingress instead.
If you want browser-initiated traces stitched from the first click, add the OpenTelemetry web SDK with its fetch instrumentation to your frontend.
Most deployments skip this and accept ingress-rooted traces for client-side navigation.

## The backend joins automatically

plone.observability extracts the incoming `traceparent` in its WSGI middleware; beyond {doc}`/how-to/enable-opentelemetry-tracing` there is nothing to configure.
The publish span, and the catalog, subrequest, transform, and commit spans below it, nest under Volto's outgoing request span.

## Continue into PostgreSQL

If your ZODB runs on zodb-pgjsonb, or anything else in the backend process talks to PostgreSQL through psycopg 3, enable the optional psycopg instrumentor to close the last gap with per-statement SQL spans.
See {ref}`sql-spans-psycopg`.

## Verify the stitched trace

Request an uncached page through the full chain, then open the trace in your tracing backend.
You should see one trace: the ingress span at the root, the Volto SSR span below it, the backend's publish span below that, and catalog or SQL spans at the bottom.
If the backend spans appear as separate traces instead, a hop dropped the `traceparent` header; header-scrubbing VCL is the usual suspect.

```{seealso}
- {doc}`/reference/tracing` for every span the backend emits and its attributes.
- {doc}`/explanation/tracing` for how the backend spans relate to the metrics.
```
