# plone.observability

<!-- diataxis: landing -->

```{image} _static/logo-400.png
:alt: plone.observability logo
:width: 200px
:align: center
```

Kubernetes-style health probes, a pluggable Prometheus and JSON metrics endpoint, and optional OpenTelemetry tracing for Plone running in containers.

Plone's built-in `@@ok` view answers `OK` whether the database is reachable or not, right up until the process is too busy to answer at all.
That is not enough to orchestrate Plone in Kubernetes.
plone.observability gives an orchestrator the real signals it needs: separate liveness, readiness, and startup probes on a dedicated port, plus a metrics endpoint your monitoring stack can scrape.

**Key capabilities:**

- Liveness, readiness, and startup probes on a separate HTTP port that stays answerable when all Zope threads are busy
- A pluggable `@@metrics` endpoint with Prometheus text and JSON output
- Request, ZODB, and content metrics out of the box, with low-cardinality labels
- Optional OpenTelemetry tracing that honors the standard `OTEL_*` environment variables
- Extensible via the Zope Component Architecture: custom health checks, metric providers, and formatters

**Requirements:** Plone 6, Python 3.10+.
OpenTelemetry tracing is an optional extra.

## Documentation

::::{grid} 2
:gutter: 3

:::{grid-item-card} Tutorials
:link: tutorials/index
:link-type: doc

**Learning-oriented** -- step-by-step lessons to build skills.

*Start here if you are new to plone.observability.*
:::

:::{grid-item-card} How-to guides
:link: how-to/index
:link-type: doc

**Goal-oriented** -- solutions to specific problems.

*Use these when you need to accomplish something.*
:::

:::{grid-item-card} Reference
:link: reference/index
:link-type: doc

**Information-oriented** -- configuration tables and API details.

*Consult when you need exact facts.*
:::

:::{grid-item-card} Explanation
:link: explanation/index
:link-type: doc

**Understanding-oriented** -- architecture and design decisions.

*Read to understand why the package works the way it does.*
:::

::::

## Quick start

1. {doc}`Get plone.observability running in Docker <tutorials/getting-started>`
2. {doc}`Install it into your own Plone and wire the WSGI filters <how-to/install>`
3. {doc}`Point Kubernetes probes at the health server <how-to/configure-kubernetes-probes>`
4. {doc}`Understand the three health probes <explanation/health-probes>`

```{toctree}
---
maxdepth: 3
caption: Documentation
titlesonly: true
hidden: true
---
ecosystem
tutorials/index
how-to/index
reference/index
explanation/index
```
