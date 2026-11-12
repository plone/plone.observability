# How to add custom spans in your code

This guide shows you how to trace your own code by opening spans from an add-on or project.
Use it when a request spends time in code that plone.observability does not already instrument.
The helper makes that time show up in your traces.

For the helper signature, see {doc}`/reference/tracing`.

(add-custom-spans-open-a-span-around-your-code)=

## Open a span around your code

Import `start_span` and wrap the work in a `with` block.

```python
from plone.observability.spans import start_span


def rebuild_report(items):
    with start_span("myaddon.rebuild_report"):
        for item in items:
            process(item)
```

The span nests automatically under whatever span is currently active, usually the `ZPublisher.publish` span for the request.
It appears in your trace backend as a child, with its own start time and duration.

(add-custom-spans-attach-attributes)=

## Attach attributes

Pass a dictionary of attributes to record context alongside the span.

```python
with start_span("myaddon.rebuild_report", {"myaddon.item_count": len(items)}):
    for item in items:
        process(item)
```

Keep attribute values bounded, as you do metric labels.
Use a count or a category.
Do not use an unbounded list of ids.

(add-custom-spans-add-attributes-or-events-during-the-span)=

## Add attributes or events during the span

`start_span` yields the span object.
You can enrich it as the work proceeds.
Without the `opentelemetry` extra installed the helper yields `None`.
Guard any use of the yielded value.

```python
with start_span("myaddon.rebuild_report") as span:
    result = run()
    if span is not None:
        span.set_attribute("myaddon.rows_written", result.rows)
```

(add-custom-spans-nest-spans)=

## Nest spans

Spans opened inside another `start_span` block nest under it.
You can break a large operation into named phases.

```python
with start_span("myaddon.import"):
    with start_span("myaddon.import.parse"):
        data = parse(source)
    with start_span("myaddon.import.store"):
        store(data)
```

(add-custom-spans-leave-it-in-production-code)=

## Leave it in production code

`start_span` is dependency-optional: when the `opentelemetry` extra is not installed it is a no-op context manager that yields `None`.
You can call it unconditionally in shipped code without adding a hard dependency on OpenTelemetry.
It costs nothing when tracing is off.

Name your spans with a stable, low-cardinality prefix such as your add-on name, for example `myaddon.import.store`.
Never put ids or other unbounded values in the span name.

```{seealso}
- {doc}`/reference/tracing` for the emitted built-in spans and the helper signature.
- {doc}`/explanation/tracing` for why the built-in spans come from Zope events and how tracing relates to metrics.
- {doc}`/how-to/enable-opentelemetry-tracing` to turn tracing on so your spans are exported.
```
