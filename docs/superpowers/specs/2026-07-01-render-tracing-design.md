# Render-phase tracing: viewlets & portlets

**Date:** 2026-07-01
**Status:** Approved (design)

## Summary

For ClassicUI (Blicca) the request time is dominated by server-side template rendering, which
is a black box in the current trace (`ZPublisher.publish → transformchain → catalog/zodb`).
Add spans for the render phase so an operator sees which **viewlet** / **viewlet manager** /
**portlet** dominates — and, via the b14 per-span ZODB counts, how many object loads each one
causes (the real N+1 signal on Postgres-backed storage).

Volto is unaffected (client-side render; the backend serves `@@…` data), so the value is
concentrated in ClassicUI — and the measured counts show it is bounded, not explosive.

## Measured counts (why this is safe)

From a standard Plone 6.2 + Barceloneta install (aaf backend) and classic.demo.plone.org:

- Viewlet **managers**: ~15–17.
- Registered **viewlets**: ~45 total, of which ~15 are cheap `<head>` entries
  (`IHtmlHead` 6, `IHtmlHeadLinks` 7, `IScripts` 1, `IHTTPHeaders` 1). Body viewlets ≈ 20–25.
- **Portlets**: ~3–8 per page (0–2 columns).

So a fully instrumented page emits **~30–40 spans** — tens, not hundreds. Span explosion only
begins *below* the viewlet level (per-macro / per-TAL-expression), which is explicitly out of
scope.

## Scope

**In:**
- One span per **viewlet manager** (all managers).
- One span per **viewlet**, for *body* managers only. For *head* managers
  (`IHtmlHead`, `IHtmlHeadLinks`, `IScripts`, `IHTTPHeaders`) emit only the manager span
  (head viewlets are cheap and numerous). Per-viewlet head spans are easy to add later if a
  problem ever surfaces there.
- One span per **portlet column/manager** and one per **portlet**.
- Each span carries the b14 ZODB delta (`plone.zodb.objects_loaded` / `_stored`) via
  `otel/dbcounts.py`.

**Out (deferred):**
- A **view-render span**. There is no clean chokepoint: wrapping only the *published* view
  misses nested `context.restrictedTraverse('@@x')()` calls; wrapping *every* `BrowserView.__call__`
  captures all `@@…`/AJAX/helper views → explosion + fragility. The viewlet/portlet spans nest
  directly under `ZPublisher.publish`, which is sufficient. Easy to add later if wanted.
- Per-macro / per-expression spans (explosion + Chameleon-internals fragility).

## Instrumentation

No render events exist, so wrap the render methods — the same sanctioned monkeypatch pattern
as `otel/catalog.py` (`register()`/`unregister()`, tracked patch list, restorable). All gated
by `is_enabled()` + `exclusions.is_suppressed()` and a feature opt-out
`PLONE_OBSERVABILITY_OTEL_RENDER` (default on when tracing is on; set `0` to keep only the
coarse trace).

Wrap points (verified against the installed packages):

- **Viewlet manager + per-viewlet:** `zope.viewlet.manager.ViewletManagerBase.render`
  (its body is `'\n'.join([viewlet.render() for viewlet in self.viewlets])`). The traced
  version opens `viewletmanager <name>`, and — unless the manager is a head manager — wraps
  each `viewlet.render()` in a `viewlet <name>` span, then joins. `self.request` gives the
  connection for the ZODB delta. `plone.app.viewletmanager` overrides only `filter/sort/update`,
  so `render` has this single definition.
- **Portlet column + per-portlet:** `plone.portlets.manager.PortletManagerRenderer.render`
  (body `"\n".join([p["renderer"].render() for p in portlets])`). The traced version opens
  `portletcolumn <name>` and wraps each portlet renderer's `render()` in `portlet <name>`.

Head-manager detection: by the manager's provided interface (`IHtmlHead`, `IHtmlHeadLinks`,
`IScripts`, `IHTTPHeaders` from `plone.app.layout.viewlets.interfaces` /
`plone.app.viewletmanager`), with a name fallback.

Soft dependency: patch a target only when its class is importable (`zope.viewlet` is always
present; `plone.portlets` is present on ClassicUI stacks). `register()` skips absent targets.

## Span names & attributes

- `viewletmanager <name>` — `plone.viewletmanager.name`, `plone.viewlet.count`.
- `viewlet <name>` — `plone.viewlet.name`.
- `portletcolumn <name>` — `plone.portletmanager.name`.
- `portlet <name>` — `plone.portlet.name`.
- Plus `plone.zodb.objects_loaded` / `plone.zodb.objects_stored` on every span (from
  `dbcounts`). Names are low-cardinality (static registry) so they are safe in the span name.

## Nesting / data flow

Rendering runs synchronously on the request thread during publish (before the response
transform chain), so the current OTel context is the `ZPublisher.publish` span. Manager and
column spans nest under it via `start_as_current_span`; viewlet spans nest under their manager
span; portlet spans under their column span; any catalog/zodb spans a viewlet/portlet triggers
nest under it automatically.

```
ZPublisher.publish
├─ viewletmanager plone.portalheader        (loads=..)
│  ├─ viewlet plone.logo
│  └─ viewlet plone.searchbox
├─ portletcolumn plone.leftcolumn
│  ├─ portlet navigation                    (loads=312)
│  └─ portlet recent
└─ viewletmanager plone.htmlhead            (head: manager span only)
```

## Error handling

Each traced method degrades to the original render on any error and never breaks rendering
(the manager already tolerates viewlet errors). Disabled/suppressed/opt-out → pure
pass-through. `unregister()` restores every patched method (used by tests and teardown).

## Testing

`tests/test_otel_rendering.py`, using the in-memory `span_exporter`:
1. A fake `ViewletManagerBase` subclass with fake viewlets → `viewletmanager <name>` +
   `viewlet <name>` children, correct nesting, `plone.viewlet.count`.
2. A head manager (marked with a head interface) → manager span only, no viewlet children.
3. A fake portlet manager renderer with fake portlet renderers → `portletcolumn` + `portlet`
   spans.
4. ZODB counts: a fake `request.PARENTS[-1]._p_jar` whose counts advance across a viewlet
   render → the viewlet span carries the delta.
5. Opt-out (`PLONE_OBSERVABILITY_OTEL_RENDER=0`) and disabled/suppressed → no render spans,
   original output returned unchanged.
6. `register()`/`unregister()` idempotency + restoration of the original methods.

## CHANGES

Towncrier `feature` fragment:

> Trace the ClassicUI render phase: emit spans per viewlet manager, per body viewlet, per
> portlet column and per portlet (head viewlet managers collapse to a single span), each
> carrying the per-span ZODB object-load counts. Off via
> `PLONE_OBSERVABILITY_OTEL_RENDER=0`.
