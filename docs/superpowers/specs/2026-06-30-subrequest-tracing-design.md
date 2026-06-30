# Tracing plone.subrequest-rendered tiles (blocks/mosaic)

**Date:** 2026-06-30
**Issue:** [#43](https://github.com/plone/plone.observability/issues/43)
**Status:** Approved (design)

## Summary

Tiles rendered via `plone.subrequest` are invisible in the trace: on a blocks/mosaic page
the `transform.plone.app.blocks.tiles` span (handler `IncludeTiles`) accounts for nearly
the whole request but has no children. We add one span per actual subrequest, nested under
the active transform span, so the per-tile cost is visible.

## Root cause (verified)

`plone.app.blocks.tiles.renderTiles()` resolves each tile via
`plone.app.blocks.utils.resolve(url)`, which calls `plone.subrequest.subrequest(url)`.
`subrequest()` clones the request and runs `request.traverse(path)` + `mapply(...)`
directly — it does **not** go through `ZPublisher.WSGIPublisher.publish` nor the WSGI
server. So neither the OTel WSGI middleware nor the `IPubStart/IPubSuccess` subscribers
(`otel/pubevents.py`) fire, and there is **no subrequest event** to subscribe to.

## Constraints

- **Soft dependency, no hard import.** The module targets `plone.subrequest` /
  `plone.app.blocks.utils` only by **module-name string** in the post-import hooks — it
  does not `import plone.subrequest` at top level. So it is safe to load even when those
  packages are absent: the hooks stay inert until (and unless) the target modules import.
  Its only hard import is `opentelemetry`, which is already gated by the `otel` subpackage
  (`zcml:condition="installed opentelemetry.sdk"`). No separate `plone.subrequest`
  condition is needed.
- **No events available** → use function wrapping. Use `wrapt.register_post_import_hook`
  (already available via `opentelemetry-instrumentation`) so wrapping is independent of
  import order — `from plone.subrequest import subrequest` callers bind the original at
  their import time, so patching must target the caller's bound name.
- Must degrade to a no-op when tracing is disabled/suppressed and must never change
  subrequest behaviour or raise.

## Components

### `src/plone/observability/otel/subrequest.py`

A shared wrapper plus post-import-hook registration:

- **`_traced_subrequest(wrapped, instance, args, kwargs)`** — wrapt-style wrapper:
  1. If `not is_enabled()` or `exclusions.is_suppressed()` → `return wrapped(*args, **kwargs)`.
  2. Resolve the URL (first positional arg or `kwargs["url"]`); compute the span name
     (see below).
  3. Determine the parent: the active single-transform span on
     `request.environ[_SINGLE_SPAN_KEY]` (imported from `otel/transformchain.py`) if
     present, else the current context. Use
     `tracer.start_as_current_span(name, context=…)`.
  4. Call `response = wrapped(*args, **kwargs)`; set attributes; return `response`.
  5. On exception: record on the span and re-raise (do not swallow).
- **`register()`** — idempotent:
  - `wrapt.register_post_import_hook(lambda m: wrapt.wrap_function_wrapper(m, "subrequest", _traced_subrequest), "plone.app.blocks.utils")`
    — the single funnel for blocks/mosaic tiles.
  - same for module `"plone.subrequest"`, attribute `"subrequest"` — fallback for other
    subrequest users (ESI, etc.).
  - The two wrapped references never chain (blocks bound the original), so each call yields
    exactly one span.

`register()` is called from the OTel activation path (process start), alongside the other
`otel` instrumentation, guarded by `is_enabled()`.

### Span shape

- **Name:** `subrequest <segment>` where `<segment>` is the last non-empty path segment of
  the URL with the query string stripped (e.g. `subrequest @@plone.app.standardtiles.html`).
  Falls back to `subrequest` if no segment can be derived. Low-cardinality (groups by tile
  view across pages); the high-cardinality content path lives in attributes.
- **Attributes:** `http.url` = full URL (path + query), `http.method` = `"GET"`,
  `http.status_code` = `response.status` (int).
- **Parent:** active transform span (→ nests under `transform.plone.app.blocks.tiles`),
  else current context (the `ZPublisher.publish` span). Nested tiles and tile-internal
  catalog/zodb spans nest automatically because the span is made current.
- **Kind:** internal.

### No span when there is no subrequest

`blocks.utils.resolve()` short-circuits on its per-request URL cache and on
`++resource++` resources without calling `subrequest`. Those produce no span, which is
correct — they cost ~nothing. Span count == unique tile URLs per request.

### ZCML

`otel/configure.zcml` already includes the otel subpackage conditionally on
`installed opentelemetry.sdk`. Within the otel activation, `subrequest.register()` runs
only when `plone.subrequest` is importable; the post-import hooks themselves are inert
until the target modules import, so registering unconditionally is safe, but we still gate
the whole `otel/subrequest` import behind the OTel extra (it imports `opentelemetry`).

## Data flow

```
ZPublisher.publish (current ctx)
└─ transformchain
   └─ transform.plone.app.blocks.tiles      (IncludeTiles; _SINGLE_SPAN_KEY set)
      ├─ subrequest @@plone.app.standardtiles.html   (parent = the tiles transform span)
      │     └─ pgcatalog query … (nests via current ctx)
      └─ subrequest @@aaf.newslist
```

## Error handling

- Wrapper never swallows: it records the exception on the span (status ERROR) and
  re-raises so `subrequest`'s own exception handling is unaffected.
- If the parent-span lookup or attribute access fails, fall back to current context /
  skip the attribute — never break the subrequest.
- Disabled/suppressed → pure pass-through, zero overhead beyond two cheap checks.

## Testing

Unit tests (no full Plone site needed; wrapt wrapper is callable directly):

1. **Span created with correct name/attributes.** Call the wrapper around a fake
   `subrequest` returning a fake response with `.status = 200`; assert one span named
   `subrequest @@tile`, attributes `http.url`, `http.method=GET`, `http.status_code=200`.
2. **Name derivation.** URLs `/a/b/@@tile?x=1` → `@@tile`; `/a/b/` → `b`; `/` or empty →
   `subrequest`. Query never in the name.
3. **Parent nesting.** With a transform span stashed on `request.environ[_SINGLE_SPAN_KEY]`,
   assert the subrequest span's parent is that span; without it, parent = current span.
4. **Disabled / suppressed → no span, pass-through** (assert the wrapped result is returned
   and no span recorded).
5. **Exception path:** wrapped raises → span status ERROR, exception recorded, re-raised.
6. **register() idempotent** and wraps both `plone.app.blocks.utils.subrequest` and
   `plone.subrequest.subrequest` (assert the attributes are wrapt wrappers after a
   simulated import).

Use an in-memory OTel `TracerProvider` + `InMemorySpanExporter` (SDK test utils) to assert
emitted spans, mirroring the existing otel tests.

## Out of scope

- Tile-specific name parsing beyond "last path segment" (decided: keep it simple).
- Instrumenting `resolve()` cache hits / `++resource++` (no cost, no span).
- OTLP metric for subrequest counts/durations (could derive from span metrics later).

## CHANGES

Towncrier news fragment under the package's news directory, type `feature`:

> Trace `plone.subrequest`-rendered tiles: emit one span per subrequest, nested under the
> active transform span, when `plone.subrequest` is installed. #43
