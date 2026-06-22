# Changes

<!-- towncrier release notes start -->

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
