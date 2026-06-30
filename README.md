# plone.observability

Kubernetes-style health probes, a pluggable Prometheus and JSON metrics endpoint, and optional OpenTelemetry tracing for Plone running in containers.

Plone's built-in `@@ok` view answers `OK` whether the database is reachable or not, right up until the process is too busy to answer at all.
plone.observability gives an orchestrator the real signals it needs: separate liveness, readiness, and startup probes on a dedicated port that stays answerable under load, plus a metrics endpoint your monitoring stack can scrape.

## Features

- Liveness, readiness, and startup probes on a separate HTTP port
- A pluggable `@@metrics` endpoint with Prometheus and JSON output
- Request, ZODB, and content metrics with low-cardinality labels
- Optional OpenTelemetry tracing that honors the standard `OTEL_*` environment variables
- Extensible via the Zope Component Architecture: custom health checks, metric providers, and formatters

## Installation

Add `plone.observability` to your dependencies, include its ZCML, and wire the WSGI filters.
See the [installation guide](https://plone.github.io/plone.observability/how-to/install.html) for the full steps.

```toml
[project]
dependencies = [
    "plone.observability",
]
```

```xml
<include package="plone.observability" />
```

## Documentation

Full documentation is at **<https://plone.github.io/plone.observability/>**:

- [How-to guides](https://plone.github.io/plone.observability/how-to/) — install, configure Kubernetes probes, scrape with Prometheus, enable tracing, extend via ZCA
- [Reference](https://plone.github.io/plone.observability/reference/) — configuration, health endpoints, metrics, tracing, interfaces
- [Explanation](https://plone.github.io/plone.observability/explanation/) — why three probes, why a separate port, label cardinality, tracing design

For LLM context, see [`llms.txt`](https://plone.github.io/plone.observability/llms.txt).

## License

GPL-2.0-only. See [LICENSE](LICENSE).
