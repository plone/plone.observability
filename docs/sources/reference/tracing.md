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
| `ZPublisher.publish` | once per request | `http.route`, `plone.published` (class name of the published object), `enduser.authenticated`, and `enduser.id` when enabled |
| `catalog.searchResults` | per catalog query | `plone.catalog.result_count` |
| `catalog.unrestrictedSearchResults` | per catalog query | `plone.catalog.result_count` |
| `transaction.commit` | per ZODB transaction completion |—|
| `transformchain` | per response-transform phase | `plone.transformchain.transform_count` |
| `transform.<name>` | per transform, child of `transformchain` | `plone.transform.name`, `plone.transform.handler` |
| `subrequest <segment>` | per `plone.subrequest` render, nested under the active transform span | `http.url`, `http.method`, `http.status_code` |
| `viewletmanager <name>` | per viewlet manager render | `plone.viewletmanager.name`, `plone.viewlet.count` |
| `viewlet <name>` | per viewlet, child of `viewletmanager`, not for the head managers | — |
| `portletcolumn <name>` | per portlet column render | `plone.portletmanager.name` |
| `portlet <name>` | per portlet, child of `portletcolumn` | — |

`<segment>` is the last path segment of the subrequest URL.
The `catalog.*` spans cover both standard Plone and plone-pgcatalog.
The `transformchain` spans are emitted only when `plone.transformchain` is installed.
The subrequest span is emitted only when `plone.subrequest` is installed.
The render spans can be turned off with `PLONE_OBSERVABILITY_OTEL_RENDER=0`.
The head viewlet managers (`IHTTPHeaders`, `IHtmlHead`, `IHtmlHeadLinks`, `IScripts`) get a span but no child span per viewlet.

Tracing requires the `opentelemetry` WSGI filter.
The filter sets up the exporter, opens the root request span, and installs the catalog, commit, subrequest, and render instrumentation.
Without it, no spans are exported.
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

## Per-span memory attributes

With `PLONE_OBSERVABILITY_REQUEST_RSS=1`, the root request span and each subrequest span carry the resident set size of the process:

| Attribute | Meaning |
|---|---|
| `plone.process.rss_start_bytes` | resident set size when the span started |
| `plone.process.rss_end_bytes` | resident set size when the application returned or the subrequest finished |
| `plone.process.rss_delta_bytes` | end minus start, negative when the resident set size shrank |

The attributes need `/proc/self/statm` (Linux).
OpenTelemetry has no semantic convention for them.
They use the `plone.` namespace.

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
