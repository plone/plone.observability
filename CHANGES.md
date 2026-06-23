# Changes

<!-- towncrier release notes start -->

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
