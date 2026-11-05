# How to add a custom metric provider

This guide shows you how to expose your own metrics through the `@@metrics` endpoint.

A metric provider is an adapter on `OFS.interfaces.IApplication` that yields `Metric` instances.
For the interface and the `Metric` fields, see {doc}`/reference/interfaces`.

## Implement the provider

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

## Register the adapter

```xml
<adapter
    factory=".metrics.MyMetricProvider"
    provides="plone.observability.interfaces.IMetricProvider"
    for="OFS.interfaces.IApplication"
    name="myapp"
    />
```

The next scrape of `@@metrics` includes the yielded metrics.

## Replace a built-in provider

Providers are named adapters, so registering an adapter under the name of a built-in provider replaces it.
Register it in your package's `overrides.zcml`, where it wins over the built-in registration instead of conflicting with it.
Plone loads that file for add-ons registered through `z3c.autoinclude` with target `plone`; otherwise include it with `includeOverrides`.


```xml
<adapter
    factory=".metrics.MyContentMetricProvider"
    provides="plone.observability.interfaces.IMetricProvider"
    for="OFS.interfaces.IApplication"
    name="content"
    />
```

Keep the metric names and labels of the provider you replace, so dashboards and alerts keep working.
A catalog backend that does not store its data per site replaces the `content` provider this way; see {doc}`/reference/metrics` for the details.

## Keep labels low-cardinality

Do not put unbounded values, such as a user id or a full URL, into metric names or labels.
Each unique combination becomes a separate Prometheus time series.
See {doc}`/explanation/metrics-design` for why this matters and what to use instead.

```{seealso}
{doc}`/reference/metrics` describes the built-in metrics and the `scope` label your provider should set.
```
