# About tracing

OpenTelemetry tracing in plone.observability is optional and stays off unless you install the extra and point it at a collector.
It is built to stay out of your way.
This page explains the design: why it is OTel-native, where the spans come from, and how tracing relates to the metrics.

(tracing-otel-native-not-a-parallel-configuration)=

## OTel-native, not a parallel configuration

Tracing honors the standard `OTEL_*` environment variables directly.
No second, package-specific way exists to set the endpoint, the service name, or the sampler.
You configure them the way you would configure any OpenTelemetry-instrumented service, and plone.observability picks them up.

The only package-specific switches are overrides: a master `PLONE_OBSERVABILITY_OTEL_ENABLED` to force tracing on or off, and a couple of toggles for the package's own defaults.
The point is that an operator who already knows OpenTelemetry does not have to learn a Plone dialect of it.

(tracing-events-where-zope-has-them-wrappers-where-it-has-none)=

## Events where Zope has them, wrappers where it has none

Wherever Zope announces a step, the spans come from its own events and hooks.
The publish span follows the ZPublisher events.
The transformchain spans follow the events of `plone.transformchain`.
The commit span comes from a transaction synchronizer.
Event-driven spans ride on interfaces Zope already publishes.
They keep working across Plone versions.

Some steps announce nothing.
Catalog tools emit no events, templates render viewlets and portlets without one, and `plone.subrequest` bypasses the publisher.
For these, the package wraps the methods that do the work.
They are the catalog query methods, the render methods of viewlet managers and portlet columns, and the `subrequest()` function.
The package also wraps `Connection.setstate` for the ZODB load time.
A wrapper is more fragile than an event subscriber when the wrapped code changes.
The package uses a wrapper only where no event exists.

The `opentelemetry` WSGI filter installs the wrappers only when tracing is enabled.
With tracing off, the request path runs the original code.

Exclusion is total.
When a path is excluded from tracing, the package suppresses span creation at both layers.
The layers are the WSGI root span and the event-driven inner spans.
An excluded path produces no spans at all.
The package's own `@@metrics` scrape is excluded by default for exactly this reason.
A scrape every thirty seconds would otherwise dominate your trace volume with noise.

(tracing-tracing-and-metrics-are-complementary)=

## Tracing and metrics are complementary

Metrics tell you *that* something is slow: a rising p99, a climbing loads-per-request ratio, an error-rate spike.
They are cheap, continuous, and aggregate.

Traces tell you *why* a particular slow request was slow.
They show which catalog query ran long, which transform dominated the render, and how a subrequest-rendered tile nested inside the parent request.
They are richer and more expensive.
You sample them.

The two are designed to hand off to each other.
You watch the metrics continuously and reach for a trace when a metric tells you where to look.
This is also why user identity lives on spans and never on metrics.
See {doc}`/explanation/metrics-design`.

```{seealso}
- {doc}`/reference/tracing` for the emitted spans and their attributes.
- {doc}`/how-to/enable-opentelemetry-tracing` to turn tracing on.
```
