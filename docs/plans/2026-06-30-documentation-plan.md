# Documentation plan: plone.observability

Status: proposal
Date: 2026-06-30
Author: Jens Klein (with Claude)
Scope: replace the 475-line `README.md` with a Diataxis-structured Sphinx docs set under `docs/sources/`, matching the cloudbrine ecosystem convention (shibuya theme, ecosystem dashboard, `llms.txt`).

---

## I. Overview

**Package:** `plone.observability` — Kubernetes-style health probes, a pluggable Prometheus/JSON metrics endpoint, and optional OpenTelemetry tracing for Plone running in containers.

**Target audiences:**

- **Operators / DevOps** — deploy Plone in Kubernetes, wire health probes, scrape Prometheus, run a tracing backend.
  This is the primary audience.
- **Plone integrators / add-on developers** — extend the package with custom health checks, metric providers, or metric formatters via the Zope Component Architecture.

**Scope boundaries:**

- In scope: installing and wiring the package, configuring probes and metrics, enabling tracing, extending via ZCA, and the conceptual background that justifies the design.
- Out of scope: teaching Kubernetes, Prometheus, or OpenTelemetry themselves (link out); deployment of the full cloudbrine stack (that lives in `cdk8s-plone` and `cloud-vinyl`).

**Why this plan exists:** the README mixes all four Diataxis quadrants in one scroll — install steps, env-var reference tables, PromQL recipes, and design rationale interleaved.
That is fine for a 50-line README but unreadable at 475 lines.
The content is good; it needs to be *split by reader need*, not deleted.

---

## II. Diataxis coverage audit

Source of facts: current `README.md`.
Source of rationale/prose: the Plone community forum post (copy the reasoning into the Explanation pages, cite via `{seealso}`).

### Topic area: Health probes

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ TUTORIAL                             │ HOW-TO GUIDE                         │
│ Folded into getting-started:         │ "Wire the health server into the     │
│ run Plone, curl /live /ready         │  WSGI pipeline" + "Configure          │
│ /startup, watch them go green.       │  Kubernetes probes" (YAML).          │
│ Status: missing                      │ Status: partial (in README)          │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ EXPLANATION                          │ REFERENCE                            │
│ "About health probes: liveness vs    │ Endpoints table, JSON response       │
│  readiness vs startup, why three,    │  schema, latch behavior of /startup. │
│  why a separate port + thread."      │ Status: partial (in README)          │
│ Status: missing (forum post = source)│                                      │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Topic area: Metrics

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ TUTORIAL                             │ HOW-TO GUIDE                         │
│ Folded into getting-started:         │ "Scrape and query with Prometheus"   │
│ open @@metrics, read the numbers.    │  (scrape_config + PromQL recipes).   │
│ Status: missing                      │ Status: partial (in README)          │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ EXPLANATION                          │ REFERENCE                            │
│ "About metrics: scope global vs      │ Built-in metrics table, scope label, │
│  instance, low-cardinality labels,   │  output formats, the duration-max     │
│  caching, ZODB load/store & conflict │  reset-on-scrape rule.               │
│  monitors, why no user identity."    │ Status: partial (in README)          │
│ Status: missing                      │                                      │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Topic area: OpenTelemetry tracing

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ TUTORIAL                             │ HOW-TO GUIDE                         │
│ n/a — advanced, optional extra;      │ "Enable distributed tracing",        │
│ no guaranteed-safe beginner path     │  "Exclude paths from tracing",        │
│ (needs an OTLP backend).             │  "Add custom spans in your code".    │
│ Status: n/a                          │ Status: partial (in README)          │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ EXPLANATION                          │ REFERENCE                            │
│ "About tracing: OTel-native, event-  │ OTEL_* + PLONE_OBSERVABILITY_OTEL_*  │
│  driven spans, no monkeypatching,    │  env vars, emitted spans + their     │
│  relationship to metrics."           │  attributes.                         │
│ Status: missing                      │ Status: partial (in README)          │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Topic area: Extensibility (ZCA)

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ TUTORIAL                             │ HOW-TO GUIDE                         │
│ n/a — for competent Plone devs,      │ "Add a custom health check",          │
│ not a learning vehicle.              │  "Add a custom metric provider",      │
│ Status: n/a                          │  "Add a custom metric formatter".     │
│                                      │ Status: partial (in README)          │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ EXPLANATION                          │ REFERENCE                            │
│ Folded into the metrics/health       │ Interfaces: ILivenessCheck,           │
│ explanation pages ("why pluggable"). │  IReadinessCheck, IMetricProvider,    │
│ Status: partial                      │  IMetricFormatter, Metric dataclass. │
│                                      │ Status: partial (in README)          │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Topic area: Configuration

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ TUTORIAL / HOW-TO                    │ REFERENCE                            │
│ Covered by the specific how-tos      │ One canonical env-var table for all  │
│ that set each variable.              │  PLONE_OBSERVABILITY_* settings.      │
│                                      │ Status: partial (in README)          │
│ EXPLANATION: n/a                     │ This is the page everything links to.│
└─────────────────────────────────────┴─────────────────────────────────────┘
```

**Gaps and splits called out:**

- No Explanation quadrant exists at all today — the forum post fills it.
- The README's "Health Probes" and "Metrics" sections each mix three quadrants in one heading; they must split into reference + how-to + explanation pages.
- Configuration env vars are scattered across four README sections; consolidate into one reference page that the how-tos link to (never duplicate the table).

---

## III. Document tree (proposed)

Mirror the ecosystem convention (`docs/sources/` as Sphinx root, shibuya theme, `ecosystem.md`, `llms.txt`).
Two folder levels, Diataxis quadrants at the top.

```
docs/sources/
├── conf.py                                 # shibuya, cyan/dark, ecosystem dropdown  [must-have]
├── index.md                                # landing page, 4 grid cards + quick start [must-have]
├── ecosystem.md                            # shared ecosystem dashboard               [must-have]
├── llms.txt                                # single-file LLM context                  [should-have]
├── glossary.md                             # probe, scope, cardinality, span, ...      [nice-to-have]
│
├── tutorials/
│   ├── index.md                            # quadrant intro                           [should-have]
│   └── getting-started.md   (Tutorial)     # install → wire filters → curl probes →   [should-have]
│                                           #   scrape @@metrics, all green
│
├── how-to/
│   ├── index.md                            # quadrant intro                           [should-have]
│   ├── install.md           (How-to)       # add dep + wire WSGI filters (cookiecutter [must-have]
│   │                                       #   + PasteDeploy + manual wrap)
│   ├── configure-kubernetes-probes.md (How-to)  # liveness/readiness/startup YAML      [must-have]
│   ├── scrape-with-prometheus.md (How-to)  # scrape_config + PromQL recipes           [should-have]
│   ├── enable-opentelemetry-tracing.md (How-to) # install extra, OTEL_* setup          [should-have]
│   ├── exclude-paths-from-tracing.md (How-to)   # OTEL_PYTHON_WSGI_EXCLUDED_URLS        [nice-to-have]
│   ├── add-custom-health-check.md (How-to) # ILivenessCheck / IReadinessCheck          [should-have]
│   ├── add-custom-metric-provider.md (How-to)   # IMetricProvider adapter               [should-have]
│   └── add-custom-metric-formatter.md (How-to)  # IMetricFormatter utility              [nice-to-have]
│
├── reference/
│   ├── index.md                            # quadrant intro                           [should-have]
│   ├── configuration.md     (Reference)    # ALL PLONE_OBSERVABILITY_* env vars        [must-have]
│   ├── health-endpoints.md  (Reference)    # /live /ready /startup, JSON schema, latch [must-have]
│   ├── metrics.md           (Reference)    # built-in metrics table, scope, formats    [must-have]
│   ├── tracing.md           (Reference)    # OTEL_* vars, emitted spans + attributes   [should-have]
│   └── interfaces.md        (Reference)    # ZCA interfaces + Metric dataclass         [should-have]
│
└── explanation/
    ├── index.md                            # quadrant intro                           [should-have]
    ├── health-probes.md     (Explanation)  # why 3 probes, why separate port/thread    [must-have]
    ├── metrics-design.md    (Explanation)  # scope, cardinality, caching, monitors     [should-have]
    └── tracing.md           (Explanation)  # OTel-native, event-driven, vs metrics     [nice-to-have]
```

The README shrinks to a ~40-line pointer (see Section VI).

---

## IV. Page specifications

Only the non-obvious pages are specified; the quadrant + description in Section III is enough for the index pages.

```
Page: how-to/install.md
Quadrant: How-to guide
Title: "How to install plone.observability"
Opening: "This guide shows you how to add plone.observability to a Plone instance and wire its WSGI filters into the pipeline."
Audience: Operators with a working Plone buildout/instance
Prerequisites: A Plone 6 instance; a zope.ini you control
Sections:
  1. Add the dependency (pyproject) + ZCML include
  2. Wire filters with cookiecutter-zope-instance (recommended; wsgi_filters dict)
  3. Wire filters with hand-written PasteDeploy (alternative tab)
  4. (optional) Manual WSGI wrapping
Cross-references: {doc}`/reference/configuration`, {doc}`/explanation/health-probes`
Notes: use tab-set for cookiecutter vs PasteDeploy. Link the cookiecutter list quirk is NOT needed here.
Estimated length: ~90 lines
```

```
Page: how-to/configure-kubernetes-probes.md
Quadrant: How-to guide
Title: "How to configure Kubernetes health probes"
Opening: "This guide shows you how to point Kubernetes liveness, readiness, and startup probes at the plone.observability health server."
Sections:
  1. Expose the health port (containerPort 8081)
  2. livenessProbe / readinessProbe / startupProbe YAML
  3. Tuning failureThreshold / periodSeconds for slow Plone startup
Cross-references: {doc}`/reference/health-endpoints`, {doc}`/explanation/health-probes`
Estimated length: ~70 lines
```

```
Page: reference/configuration.md
Quadrant: Reference
Title: "Configuration"
Content: the single canonical env-var table — every PLONE_OBSERVABILITY_* variable
  (health host/port, metrics allowlist, trusted proxies, metrics cache TTL,
  zodb activity monitor, all OTEL master switches). Mandatory language, no instruction.
Note: this is the link target for every how-to. Do NOT duplicate rows elsewhere.
Estimated length: ~60 lines
```

```
Page: reference/metrics.md
Quadrant: Reference
Title: "Metrics"
Content:
  - built-in metrics table (name / type / scope / description), verbatim from README
  - the auth label rule
  - scope label values (global vs instance) as a definition list
  - output formats (Prometheus text default, ?format=json, Accept header)
  - the request_duration_seconds_max reset-on-scrape rule (factual statement; the
    "why" goes to explanation/metrics-design)
Estimated length: ~110 lines
```

```
Page: explanation/health-probes.md
Quadrant: Explanation
Title: "About health probes"
Source: the Plone community forum post — copy the reasoning, rephrase to doc style.
Content (discursive):
  - the @@ok problem: returns OK whether ZODB is reachable or not, right up until
    the process can't answer at all
  - why three probes: liveness (no deps, failure = restart), readiness (ZODB,
    failure = drain traffic), startup (latches, protects slow boot)
  - why a separate port + daemon thread: stays answerable when all WSGI threads
    are saturated, preventing false restarts
  - why metrics deliberately sit on the MAIN port (they NEED DB connectivity;
    health checks must survive its loss) — the intentional contrast
Cross-references: {doc}`/reference/health-endpoints`, {doc}`/how-to/configure-kubernetes-probes`
{seealso}: link the forum post
Estimated length: ~90 lines
```

```
Page: explanation/metrics-design.md
Quadrant: Explanation
Title: "About metrics and cardinality"
Source: forum post + README narrative paragraphs.
Content:
  - low-cardinality labels: why user identity is never a metric label (Prometheus
    blow-up) — only ever a span attribute
  - global vs instance scope: what it means for aggregation, double-counting
  - the metrics cache TTL: why catalog counts and DB-wide ZODB gauges are expensive
  - the ZODB activity monitor: storage-agnostic load/store counters, install-only-
    if-absent rule
  - conflict metrics: read vs write conflicts, retry true/false
Cross-references: {doc}`/reference/metrics`, {doc}`/reference/configuration`
Estimated length: ~110 lines
```

---

## V. Prioritized roadmap

**Phase 1 — must-have (a usable docs site; operator can install and run).**
In dependency order:

1. `conf.py`, `index.md`, `ecosystem.md` — scaffold (copy from a sibling, adapt strings + logo).
2. `reference/configuration.md` — the table everything links to.
3. `reference/health-endpoints.md`, `reference/metrics.md`.
4. `how-to/install.md` (depends on reference/configuration).
5. `how-to/configure-kubernetes-probes.md` (depends on reference/health-endpoints).
6. `explanation/health-probes.md` (the forum-post content — the headline "real docs" win).
7. Shrink `README.md` to a pointer.

**Phase 2 — should-have (rounds out all four quadrants).**

8. `tutorials/getting-started.md`, `tutorials/index.md`.
9. `how-to/scrape-with-prometheus.md`.
10. `reference/tracing.md`, `how-to/enable-opentelemetry-tracing.md`.
11. `reference/interfaces.md`, then `how-to/add-custom-health-check.md` and `how-to/add-custom-metric-provider.md`.
12. `explanation/metrics-design.md`.
13. `how-to/index.md`, `reference/index.md`, `explanation/index.md`.
14. `llms.txt`.

**Phase 3 — nice-to-have (completeness).**

15. `explanation/tracing.md`.
16. `how-to/exclude-paths-from-tracing.md`, `how-to/add-custom-metric-formatter.md`.
17. `glossary.md`.

---

## VI. Style and consistency notes

**Ecosystem deviations from stock Plone docs conventions (intentional, match siblings):**

- **Theme is `shibuya`, not `plone-sphinx-theme`.** All cloudbrine packages share shibuya with `accent_color: cyan`, `color_mode: dark`, and the `ecosystem-dashboard` extension. Follow that, not the generic Plone theme guidance.
- **No `html_meta` frontmatter.** Shibuya + OpenGraph fallbacks handle social cards; siblings do not carry the Plone-core `html_meta` block. Skip it.
- **Ecosystem nav dropdown** in `html_theme_options.nav_links` must list all packages, identical across repos — copy the block from `zodb-pgjsonb/docs/sources/conf.py` and adjust `logo_target`.
- **`ecosystem.md` + `llms.txt`** are ecosystem conventions — include both.

**Conventions that DO apply (from plone-doc-style):**

- One sentence per line. American English. Active voice, imperative mood. Sentence-case headings. Dashed filenames.
- Diataxis: one quadrant per page. The how-to pages link to `reference/configuration` for env vars — never re-print the table.
- Code blocks: `console` for sessions with output, `shell` for bare commands (no `$` prompts), `yaml`/`python`/`xml`/`promql`/`ini` elsewhere. No ellipses, no JSON comments.
- Admonitions sparingly (1–2 per page). Use `{seealso}` to cite the forum post rather than linking it as a bare blog link in prose.
- Tabs for alternative paths to the same outcome (cookiecutter vs PasteDeploy install).

**Glossary terms to define:** liveness probe, readiness probe, startup probe, scrape, cardinality, scope (global/instance), span, activity monitor.

**Vale / linkcheck:** siblings ship `.vale.ini` + a docs `Makefile`/`include.mk` (mxmake-generated). Copy them so `make docs-vale` and linkcheck work; note that CI does not hard-fail on Vale (`--no-exit`).

---

## Decisions (locked 2026-06-30)

1. **Repo home: `plone/plone.observability`** (NOT under the `bluedynamics` org).
   Consequences for `conf.py`:
   - `repository_url` / GitHub nav link / issue links → `https://github.com/plone/plone.observability`.
   - Docs host URL is still TBD but under the plone org (likely `plone.github.io/plone.observability/` or a ReadTheDocs target); pick the host before wiring absolute URLs in the ecosystem dropdown.
   - The shared ecosystem nav dropdown currently omits observability — **add an entry for it** when copying the block from a sibling, pointing at the chosen plone-org docs URL.
2. **Own logo.** observability gets its own `_static/logo-web.png` + `_static/logo-400.png` + `favicon.ico`.
   Jens delivers the asset later — scaffold `conf.py`/`index.md` to reference `_static/logo-web.png` now and drop the file in when it arrives.

## Resolved: tutorial realism (2026-06-30)

`getting-started.md` builds on the **official `plone/plone-backend` image via Docker Compose**.
`ADDONS=plone.observability` installs the add-on at container start and its ZCML autoloads (`z3c.autoinclude` target `plone`).
The image's `zope.ini` has no WSGI-filter knob, so the Compose file ships a `zope.ini` (inline via Compose `configs:`) that wires the `healthserver` and `observability` filters into `[pipeline:main]`.
Verified end to end: all three probes return green and `@@metrics` serves Prometheus + JSON.
The verified Compose file is committed at `docs/sources/tutorials/_assets/docker-compose.yml`.
