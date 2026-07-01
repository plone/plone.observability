# Changes

<!-- towncrier release notes start -->

## 1.0.0b15 (2026-07-01)

### New features:

- Add ``plone.zodb.load_time_ms`` to every span that already carries the ZODB object counts (publish, subrequest, viewlet/portlet render): the time spent materialising objects (round-trip + decode), so per-tile/per-request object-load cost is visible in traces.
- Trace the ClassicUI render phase: emit spans per viewlet manager, per body viewlet, per portlet column and per portlet (head viewlet managers collapse to a single span), each carrying the per-span ZODB object-load counts. Disable with ``PLONE_OBSERVABILITY_OTEL_RENDER=0``.

### Documentation:

- Add a how-to guide, *How to add custom spans in your code*, covering the `start_span` helper for instrumenting add-on and project code with OpenTelemetry spans.


## 1.0.0b14 (2026-07-01)

### New features:

- Record objects loaded/stored per span (``plone.zodb.objects_loaded`` / ``plone.zodb.objects_stored``) on the publish span (request total) and each subrequest span (per-tile delta), making N+1 object-load cost visible in traces. ([#49](https://github.com/plone/plone.observability/issues/49))

### Internal:

- Add a `Documentation` GitHub Actions workflow that builds the Sphinx docs with uv and deploys them to GitHub Pages on every push to `main` that touches `docs/**`, matching the convention used across the cloudbrine ecosystem repositories.
- Exclude ``docs/`` from the zpretty pre-commit hook: its Sphinx/Jinja HTML templates are not ZCML/Zope page templates.

### Documentation:

- Replace the single long `README.md` with a structured Sphinx documentation site under `docs/sources/`, organized by the Diataxis framework (tutorials, how-to, reference, explanation) and matching the cloudbrine ecosystem convention (shibuya theme, ecosystem dashboard, `llms.txt`). The `README.md` is now a short pointer to the docs site.


## 1.0.0b13 (2026-06-30)

### Bug fixes:

- Fix the `/startup` probe never turning green under Kubernetes. `/startup` reported success only after `/ready` had been polled and passed at least once, but Kubernetes does not run the readiness probe until the startup probe has already succeeded — a chicken-and-egg that left pods stuck in *starting* for the whole startup-probe budget (CPU idle, since Plone had finished booting). `/startup` now evaluates the readiness checks itself and latches on first success, so it stands on its own. Thanks to Afonso on the Plone community forum for the report and a clear repro. ([#46](https://github.com/plone/plone.observability/issues/46))


## 1.0.0b12 (2026-06-30)

### New features:

- Trace ``plone.subrequest``-rendered tiles: emit one span per subrequest, nested under the active transform span, when ``plone.subrequest`` is installed. ([#43](https://github.com/plone/plone.observability/issues/43))


## 1.0.0b11 (2026-06-30)

### Bug fixes:

- Stop tracing the package's own `@@metrics` scrape and let operators exclude other paths. The bare `OpenTelemetryMiddleware` has no excluded-URL support, so every request — including the Prometheus scrape every ~30s — was traced and dominated trace volume. The OTel filter now honours the standard `OTEL_PYTHON_WSGI_EXCLUDED_URLS` / `OTEL_PYTHON_EXCLUDED_URLS` env vars and excludes `@@metrics` by default (turn defaults off with `PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS=0`). Because the publishing/catalog/zodb/transformchain spans are created from Zope events independently of the WSGI middleware, excluded requests are also marked suppressed in the OTel context so those subscribers skip span creation too — an excluded path produces no spans at all, not just a missing outer span. ([#40](https://github.com/plone/plone.observability/issues/40))


## 1.0.0b10 (2026-06-30)

### New features:

- Trace the `plone.transformchain` response-transform phase. When `plone.transformchain` is installed, the package now emits a `transformchain` span with one `transform.<name>` child span per transform (carrying `plone.transform.name`/`plone.transform.handler`, and `plone.transformchain.transform_count` on the parent), nested under the `ZPublisher.publish` span. This surfaces which transform (e.g. the Diazo/theming transform) dominates the post-render time. It is driven by transformchain's own before/after events — no monkeypatching — and is gated by the same OTel activation switch as the other spans.


## 1.0.0b9 (2026-06-29)

### Bug fixes:

- `@@metrics` is no longer slow on Postgres-backed storage (zodb-pgjsonb / RelStorage). The two DB-wide ZODB gauges — `plone_zodb_object_count` and `plone_zodb_db_size_bytes` — were recomputed uncached on every scrape; on FileStorage that is cheap, but on Postgres-backed storage `objectCount()`/`getSize()` become full-table/relation-size queries that took ~seconds each scrape. They are now cached at module level with a TTL (the existing `PLONE_OBSERVABILITY_METRICS_CACHE_TTL`, default 60s), keyed by database name. The cheap in-memory gauges and the load/store counters stay live per scrape. ([#35](https://github.com/plone/plone.observability/issues/35))


## 1.0.0b8 (2026-06-29)

### Bug fixes:

- Health server no longer dumps `BrokenPipeError`/`ConnectionResetError` tracebacks when a probe client disconnects before the response is fully written (common during warmup when readiness returns 503). These connection drops are now logged at debug level instead.


## 1.0.0b7 (2026-06-25)

### New features:

- Add `plone_request_duration_seconds_max{auth="authenticated|anonymous"}` — a per-scrape-window gauge of the worst-case request duration. A histogram can only bound latency to its bucket edges, so the true maximum is now tracked directly and reset on every scrape, giving operators the real max backend response time alongside the `histogram_quantile`-derived p90/p99. ([#17](https://github.com/plone/plone.observability/issues/17))


## 1.0.0b6 (2026-06-25)

### New features:

- Add `plone_zodb_conflicts_total{retry="true|false"}` — a storage-agnostic counter of ZODB ConflictErrors during request publication (including the silently-retried ones), captured via an IPubBeforeAbort subscriber. ([#26](https://github.com/plone/plone.observability/issues/26))

### Bug fixes:

- ZODB load/store metrics are now storage-agnostic: `plone_zodb_loads_total`/`plone_zodb_stores_total` counters come from a minimal, O(1) ZODB activity monitor (works on FileStorage, RelStorage, zodb-pgjsonb), replacing the FileStorage-only metrics. Installed by default unless a monitor already exists; disable with `PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR=0`. The content provider now steps aside silently on non-ZCatalog backends (which ship their own provider). ([#25](https://github.com/plone/plone.observability/issues/25))

### Internal:

- Adopt the shared ruff ruleset (single-line imports, B/SIM/UP/C4, py310 target), format ZCML with zpretty, run pre-commit as the single source in CI, and gate test coverage at 90%.


## 1.0.0b5 (2026-06-24)

### Bug fixes:

- Declare the `z3c.autoinclude.plugin` entry point (`target = plone`) so the package's ZCML — the `@@metrics` view, metric providers, OpenTelemetry and auth subscribers, and the `zodb` readiness check — loads automatically on a standard Plone instance instead of staying dormant after `pip install`. ([#21](https://github.com/plone/plone.observability/issues/21))


## 1.0.0b4 (2026-06-24)

### Breaking changes:

- The health server and OpenTelemetry activation now start from the WSGI pipeline filters instead of Zope process startup, so `zconsole`/script runs no longer bind the health port or patch the catalog. **Upgrade:** add the `egg:plone.observability#healthserver` filter to your pipeline, otherwise the health server no longer starts. ([#16](https://github.com/plone/plone.observability/issues/16))

### Bug fixes:

- Emit `plone_info` as a `gauge` instead of the OpenMetrics-only `info` type. The `@@metrics` endpoint advertises classic Prometheus exposition format (`text/plain; version=0.0.4`), in which `info` is invalid, so Prometheus rejected the **entire** scrape with `invalid metric type "info"`. `plone_info` now follows the conventional `*_info` gauge pattern (constant value 1, version in labels). ([#18](https://github.com/plone/plone.observability/issues/18))


## 1.0.0b3 (2026-06-22)

### New features:

- Add an `auth="authenticated"|"anonymous"` label to all request metrics, and `enduser.authenticated` (plus opt-in `enduser.id` via `PLONE_OBSERVABILITY_OTEL_USER_ID`) to the publish trace span.


## 1.0.0b2 (2026-06-22)

### Documentation:

- Document the recommended way to wire the WSGI filters (request metrics and the OpenTelemetry root request span) via cookiecutter-zope-instance 3.1.0+ `wsgi_filters`, instead of hand-editing `zope.ini`.


## 1.0.0b1 (2026-06-18)

### New features:

- Add optional `[opentelemetry]` extra: distributed tracing (root request, publishing, catalog query, and ZODB commit spans) with OTel-native configuration. Catalog tracing is backend-agnostic, covering both standard ZCatalog-based Plone and plone-pgcatalog. No-op when the extra is not installed. ([#2](https://github.com/plone/plone.observability/issues/2))
- Initial release: Kubernetes-style health probes (`/live`, `/ready`, `/startup`) on a separate daemon-thread port that survives worker exhaustion, plus a pluggable `@@metrics` endpoint with Prometheus and JSON output and ZCA-extensible health checks, metric providers, and formatters.
