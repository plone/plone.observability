# How to trace one request across the whole stack

This guide shows you how to stitch the ingress, the HTTP cache, the Volto frontend, the Plone backend, and PostgreSQL into a single distributed trace.

The glue is W3C Trace Context: every hop forwards the `traceparent` request header, emits its own spans, and exports them to one shared collector.
A hop that cannot emit spans but forwards the header stays invisible in the trace without breaking it.
The backend needs no propagation setup at all.
The WSGI middleware extracts an incoming `traceparent` automatically.

(trace-across-the-stack-prerequisites)=

## Prerequisites

- Backend tracing is enabled per {doc}`/how-to/enable-opentelemetry-tracing`.
- Every service can reach one OTLP collector, such as an OpenTelemetry Collector fanning out to Grafana Tempo or Jaeger.

Give each service its own service name (`traefik`, `volto`, `plone-backend`) so the trace view shows who is who.

(trace-across-the-stack-start-the-trace-at-the-ingress)=

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
The SDKs further down sample parent-based by default.
They follow the decision of the ingress.
You never get partial traces.

(trace-across-the-stack-let-varnish-pass-the-context-through)=

## Let Varnish pass the context through

Open-source Varnish emits no spans.
It does forward request headers it does not know.
The trace survives the cache without configuration.
If your VCL (Varnish Configuration Language) scrubs request headers, keep `traceparent` and `tracestate`.

Varnish answers a cache hit without touching the backend.
A cache hit produces no downstream spans.
The time spent in Varnish shows up as the gap between the ingress span and the first downstream span.
To get the hit/miss outcome on the trace, emit an `X-Cache` response header from VCL.
Record it on the ingress span with Traefik's `tracing.capturedResponseHeaders` option.
If you need real cache spans, Varnish Enterprise ships native OpenTelemetry support.

(trace-across-the-stack-trace-the-volto-server)=

## Trace the Volto server

The Node SSR (server-side rendering) process joins the trace through the OpenTelemetry Node auto-instrumentation.
Volto itself needs no code changes.
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

After hydration the browser calls `++api++` directly.
Those requests start their trace at the ingress instead.
If you want browser-initiated traces stitched from the first click, add the OpenTelemetry web SDK with its fetch instrumentation to your frontend.
Most deployments skip this and accept ingress-rooted traces for client-side navigation.

(trace-across-the-stack-the-backend-joins-automatically)=

## The backend joins automatically

plone.observability extracts the incoming `traceparent` in its WSGI middleware.
Beyond {doc}`/how-to/enable-opentelemetry-tracing` there is nothing to configure.
The publish span, and the catalog, subrequest, transform, and commit spans below it, nest under Volto's outgoing request span.

(trace-across-the-stack-continue-into-postgresql)=

## Continue into PostgreSQL

Enable the optional psycopg instrumentor if your ZODB runs on zodb-pgjsonb.
Enable it too if anything else in the backend process talks to PostgreSQL through psycopg 3.
The instrumentor closes the last gap with per-statement SQL spans.
See {ref}`sql-spans-psycopg`.

(trace-across-the-stack-verify-the-stitched-trace)=

## Verify the stitched trace

Request an uncached page through the full chain, then open the trace in your tracing backend.
You should see one trace.
The ingress span is at the root.
The Volto SSR span sits below it.
The backend's publish span is below that, with catalog or SQL spans at the bottom.
If the backend spans appear as separate traces instead, a hop dropped the `traceparent` header.
Header-scrubbing VCL is the usual suspect.

```{seealso}
- {doc}`/reference/tracing` for every span the backend emits and its attributes.
- {doc}`/explanation/tracing` for how the backend spans relate to the metrics.
```
