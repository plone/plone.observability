# About tracing

OpenTelemetry tracing in plone.observability is optional, off unless you install the extra and point it at a collector, and deliberately built to stay out of your way.
This page explains the design: why it is OTel-native, why the spans come from Zope events rather than monkeypatching, and how tracing relates to the metrics.

## OTel-native, not a parallel configuration

Tracing honors the standard `OTEL_*` environment variables directly.
No second, package-specific way exists to set the endpoint, the service name, or the sampler.
You configure them the way you would configure any OpenTelemetry-instrumented service, and plone.observability picks them up.

The only package-specific switches are overrides: a master `PLONE_OBSERVABILITY_OTEL_ENABLED` to force tracing on or off, and a couple of toggles for the package's own defaults.
The point is that an operator who already knows OpenTelemetry does not have to learn a Plone dialect of it.

## Spans from events, not monkeypatching

The interesting spans—the publish span, the catalog query spans, the transaction commit span, the transformchain spans—are created from Zope's own events and notifications.
Nothing is monkeypatched.

This matters for trust and longevity.
Instrumentation that wraps or replaces framework functions breaks quietly when the framework changes underneath it, and it can change behavior in ways that are hard to reason about.
Event-driven spans ride on interfaces Zope already publishes, so they keep working across Plone versions and never alter the request path when tracing is off.

It also means exclusion is total.
When a path is excluded from tracing, the package suppresses span creation at both layers—the WSGI root span and the event-driven inner spans—so an excluded path produces no spans at all, not just a missing outer span.
The package's own `@@metrics` scrape is excluded by default for exactly this reason: a scrape every thirty seconds would otherwise dominate your trace volume with noise.

## Tracing and metrics are complementary

Metrics tell you *that* something is slow: a rising p99, a climbing loads-per-request ratio, an error-rate spike.
They are cheap, continuous, and aggregate.

Traces tell you *why* a particular slow request was slow: which catalog query ran long, which transform dominated the render, how a subrequest-rendered tile nested inside the parent request.
They are richer and more expensive, and you sample them.

The two are designed to hand off to each other.
You watch the metrics continuously and reach for a trace when a metric tells you where to look.
This is also why user identity lives on spans and never on metrics—see {doc}`/explanation/metrics-design`.

```{seealso}
- {doc}`/reference/tracing` for the emitted spans and their attributes.
- {doc}`/how-to/enable-opentelemetry-tracing` to turn tracing on.
```
