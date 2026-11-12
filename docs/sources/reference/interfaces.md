# Interfaces

plone.observability registers all of its components through the Zope Component Architecture.
Third-party packages extend or replace any of them.
This page describes the interfaces.
These pages show how to register implementations: {doc}`/how-to/add-custom-health-check`, {doc}`/how-to/add-custom-metric-provider`, and {doc}`/how-to/add-custom-metric-formatter`.

## `ILivenessCheck`

A named utility that reports whether the process is fundamentally alive.

A liveness check must not access ZODB and must not block.

```{list-table}
:header-rows: 1

* - Member
  - Description
* - `name`
  - The check name, reported in the `/live` response.
* - `__call__()`
  - Returns a `(ok: bool, message: str)` tuple.
```

## `IReadinessCheck`

A named utility that reports whether the process can serve requests.

A readiness check may access ZODB.

```{list-table}
:header-rows: 1

* - Member
  - Description
* - `name`
  - The check name, reported in the `/ready` and `/startup` responses.
* - `__call__()`
  - Returns a `(ok: bool, message: str)` tuple.
```

## `IMetricProvider`

An adapter on `OFS.interfaces.IApplication` that yields metrics.

```{list-table}
:header-rows: 1

* - Member
  - Description
* - `name`
  - The provider name, used for registration.
* - `scope`
  - Default scope for the provider's metrics, `"instance"` or `"global"`.
* - `collect()`
  - A generator yielding `Metric` instances.
```

## `IMetricFormatter`

A named utility that serializes metrics to a wire format.

```{list-table}
:header-rows: 1

* - Member
  - Description
* - `content_type`
  - The MIME type of the produced output.
* - `format(metrics)`
  - Returns the serialized string for an iterable of `Metric` instances.
```

The formatter name is selected with the `format` query-string parameter on `@@metrics`.

## `Metric`

The value object yielded by metric providers.

```{list-table}
:header-rows: 1

* - Field
  - Description
* - `name`
  - The metric name, for example `myapp_queue_length`.
* - `value`
  - The numeric value.
* - `type`
  - The metric type: `gauge` or `counter`.
* - `scope`
  - `"instance"` or `"global"`.
* - `help`
  - A human-readable description.
* - `labels`
  - A dictionary of label names and values. Default: empty.
```

The Prometheus text format has no `info` type.
A metric with `type="info"` makes Prometheus reject the whole scrape.
Report version or build information as a `gauge` with the value `1` and the details in `labels`, as `plone_info` does.
A histogram is reported as counters named `<name>_bucket` with an `le` label, `<name>_sum`, and `<name>_count`.

Import it from `plone.observability.metric`.

## `start_span`

A dependency-optional helper for opening custom trace spans.
It is a no-op when the `opentelemetry` extra is not installed.
See {doc}`/reference/tracing`.
