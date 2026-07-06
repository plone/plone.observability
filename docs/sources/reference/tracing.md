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

## Per-span ZODB attributes

The `ZPublisher.publish` span (request total), each subrequest span (per-tile delta), and each render span carry per-span ZODB object-load counts:

| Attribute | Meaning |
|---|---|
| `plone.zodb.objects_loaded` | objects materialised (loaded) within the span |
| `plone.zodb.objects_stored` | objects stored within the span |
| `plone.zodb.load_time_ms` | time spent materialising objects (round-trip + decode) |
| `plone.zodb.load_l2_hits` | objects served from zodb-pgjsonb's shared (L2) cache |
| `plone.zodb.load_pg_objects` | objects fetched from PostgreSQL |
| `plone.zodb.load_pg_queries` | PostgreSQL round-trips (queries) |

The last three require zodb-pgjsonb (>= 1.16.0 for `load_pg_queries`); on other storages they read as 0 (best-effort, no dependency).
`load_pg_objects / load_pg_queries` is objects-per-round-trip: ≈ 1 signals an N+1 pattern, ≫ 1 signals well-batched loads (`load_multiple`/`prefetch`), so `prefetch` adoption is visible without a wall-time A/B.

## Custom spans

Application code can open child spans with a dependency-optional helper.
It is a no-op when the extra is not installed.

```python
from plone.observability.spans import start_span

with start_span("myapp.expensive_step", {"items": n}):
    do_work()
```

`start_span(name, attributes=None)` is a context manager.
It opens a child of the currently active span and yields the span object, or `None` when the `opentelemetry` extra is not installed.

```{seealso}
- {doc}`/how-to/add-custom-spans` walks through instrumenting your own code.
- {doc}`/explanation/tracing` explains why the built-in spans come from Zope events and how tracing relates to metrics.
```
