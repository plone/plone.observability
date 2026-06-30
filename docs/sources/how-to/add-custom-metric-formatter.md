# How to add a custom metric formatter

This guide shows you how to add a new wire format for the `@@metrics` endpoint, alongside the built-in Prometheus text and JSON formats.

A formatter is a named utility implementing `IMetricFormatter`.
The utility name becomes the value of the `format` query-string parameter.
For the interface members, see {doc}`/reference/interfaces`.

## Implement the formatter

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

## Register the utility

```xml
<utility
    factory=".formatters.CSVFormatter"
    provides="plone.observability.interfaces.IMetricFormatter"
    name="csv"
    />
```

## Use it

Select the format by name with the `format` query-string parameter.

```text
http://your-plone-host/@@metrics?format=csv
```

```{seealso}
{doc}`/reference/metrics` describes the endpoint and the default formats.
```
