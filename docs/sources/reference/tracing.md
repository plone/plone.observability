# Tracing

OpenTelemetry tracing is an optional extra.
Install it with:

```shell
pip install "plone.observability[opentelemetry]"
```

Tracing is OTel-native: it honors the standard `OTEL_*` environment variables and activates when the extra is installed and an OTLP endpoint is configured.
The environment variables are listed in {doc}`/reference/configuration`.

## Emitted spans

| Span | Emitted | Key attributes |
|---|---|---|
| root request span | per request, from the WSGI filter | standard HTTP attributes |
| `ZPublisher.publish` | once per request | `http.route`, `enduser.authenticated`, and `enduser.id` when enabled |
| `catalog.searchResults` | per catalog query | `plone.catalog.result_count` |
| `catalog.unrestrictedSearchResults` | per catalog query | `plone.catalog.result_count` |
| `transaction.commit` | per ZODB transaction completion |—|
| `transformchain` | per response-transform phase | `plone.transformchain.transform_count` |
| `transform.<name>` | per transform, child of `transformchain` | `plone.transform.name`, `plone.transform.handler` |
| subrequest span | per `plone.subrequest` render, nested under the active transform span |—|

The `catalog.*` spans cover both standard Plone and plone-pgcatalog.
The `transformchain` spans are emitted only when `plone.transformchain` is installed, and the subrequest span only when `plone.subrequest` is installed.

The root request span requires the `opentelemetry` WSGI filter.
Without it you still get the publishing, catalog, and commit spans, which are registered through ZCML, but not the outer WSGI span.
See {doc}`/how-to/enable-opentelemetry-tracing`.

## Custom spans

Application code can open child spans with a dependency-optional helper.
It is a no-op when the extra is not installed.

```python
from plone.observability.spans import start_span

with start_span("myapp.expensive_step", {"items": n}):
    do_work()
```

```{seealso}
{doc}`/explanation/tracing` explains why the spans come from Zope events and how tracing relates to metrics.
```
