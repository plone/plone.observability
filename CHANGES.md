# Changes

<!-- towncrier release notes start -->

## 1.2.0 (2026-10-24)

### New features:

- Add `plone_zodb_connections_idle`, the idle connections waiting in the pool, and
  `plone_zodb_pool_size`, the `pool-size` setting. Connections in use are
  `plone_zodb_connections - plone_zodb_connections_idle`. ([#80](https://github.com/plone/plone.observability/issues/80))
- Add `plone_process_rss_peak_bytes`, the peak resident set size of the process.
  On macOS the value is now correctly in bytes (`ru_maxrss` is not in KiB there). ([#81](https://github.com/plone/plone.observability/issues/81))

### Bug fixes:

- Run the readiness checks single-flight: `/ready` and `/startup` share one run at
  a time, and probes that arrive during a run answer at once with the last result,
  or with 503 once the run counts as stuck. Before, every probe got its own thread
  and opened a ZODB connection, so a blocking `db.open()` (e.g. during a database
  failover) piled up probe threads without limit; in production that kept a short
  failover from ever recovering. Results are cached for
  `PLONE_OBSERVABILITY_READINESS_CACHE_TTL` seconds (default 2), and a run counts
  as stuck after `PLONE_OBSERVABILITY_READINESS_STUCK_AFTER` seconds (default 10). ([#79](https://github.com/plone/plone.observability/issues/79))
- `plone_zodb_connections` now reports the number of open ZODB connections, in use
  or idle in the pool. It used to report the `pool-size` setting, so it was
  constant and the same on every instance. ([#80](https://github.com/plone/plone.observability/issues/80))
- `plone_process_rss_bytes` now reports the current resident set size, read from
  `/proc/self/statm`. It used to report `ru_maxrss`, the peak, so it never went
  down when memory was freed. On platforms without `/proc` the metric is left out
  instead of reporting the peak under this name.
  `plone_zodb_cache_size_bytes` now reports the estimated size of the object
  caches, summed over all connections. It used to report the configured
  `cache-size-bytes` limit, which is 0 unless set. ([#81](https://github.com/plone/plone.observability/issues/81))

### Documentation:

- Add `plone.registryfromenviron` to the ecosystem dashboard under *Tools &
  Libraries*: it overrides `plone.registry` values from environment variables.
  The dashboard is duplicated in zodb-pgjsonb, and both copies got the same card.


## 1.1.0 (2026-09-18)

### New features:

- Add an optional psycopg instrumentor: with the new ``opentelemetry-db`` extra
  installed and ``PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS=1``, every PostgreSQL
  statement (e.g. ZODB loads/stores and catalog queries under zodb-pgjsonb)
  becomes a child span of the current request span. Instrumentors now also check
  that the instrumented library itself is installed, not just the instrumentation
  package. ([#74](https://github.com/plone/plone.observability/issues/74))

### Internal:

- Deploy the documentation on `release: published` as well, so every release
  republishes the docs with the freshly bumped version. Release PRs do not touch
  `docs/**`, so the push trigger alone left the site on the previous version
  until the next docs commit.

### Documentation:

- Add a how-to guide, *How to trace one request across the whole stack*, covering
  W3C trace-context propagation through the ingress (Traefik), Varnish, the Volto
  SSR server, the backend, and down to per-statement PostgreSQL spans.
- Read the documentation version from `pyproject.toml` instead of a hardcoded
  string in `conf.py`, which had been stuck at 1.0.0b13. The published docs now
  always show the released version.


## 1.0.0 (2026-09-14)

First stable release. The package graduates from beta: the development status
classifier is now *Production/Stable*. Functionally identical to 1.0.0b18.

### Internal:

- Bump `hynek/build-and-inspect-python-package` from v2 to v3.0.1. Hatchling now emits `Metadata-Version: 2.5`, which the Twine bundled in v2 rejects, failing the release build. v3 ships Twine 7, which supports it.
- Enable ruff's cyclomatic-complexity check (`C901`, mccabe) with `max-complexity = 15`. The code base passes as-is.
- Lower ruff's C901 max-complexity threshold from 15 to 13 as part of the ecosystem-wide complexity ratchet. The code base passes as-is.

### Documentation:

- Add `cloud-vinyl` to the ecosystem dashboard and to the ecosystem navigation
  dropdown in the docs, and move the `plone.observability` dashboard entry after
  the *Deployment* group so both copies of the dashboard stay in sync.


## 1.0.0b18 (2026-07-06)

### New features:

- Rename the misnamed ``plone.zodb.load_pg_queries`` span attribute (it counted objects) to ``plone.zodb.load_pg_objects``, and add a real ``plone.zodb.load_pg_queries`` reading zodb-pgjsonb's new ``_pg_query_count`` (PostgreSQL round-trips, >= 1.16.0). Their ratio (``load_pg_objects / load_pg_queries``) makes batching/prefetch visible per span. ([#96](https://github.com/plone/plone.observability/issues/96))


## 1.0.0b17 (2026-07-02)

### New features:

- Add `plone.zodb.load_l2_hits` and `plone.zodb.load_pg_queries` span attributes.
  When running on zodb-pgjsonb (>= 1.14.3), these split `plone.zodb.objects_loaded`
  into shared-cache (L2) hits vs actual PostgreSQL fetches, so the shared-cache hit
  ratio (`l2 / (l2 + pg)`) is visible per span — attributing load-time outliers to a
  cold/gated cache (all PG) vs high per-load latency (few PG, but slow). Read
  best-effort via `getattr`, so it is a no-op on other storages (no new dependency).


## 1.0.0b16 (2026-07-02)

### New features:

- Optionally enable the standard OpenTelemetry I/O instrumentors (botocore, requests, urllib3, httpx) via ``PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS=1`` so S3 blob access and outbound HTTP become child spans in the same trace. Install the instrumentation packages via the new ``opentelemetry-io`` extra. ([#50](https://github.com/plone/plone.observability/issues/50))


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
