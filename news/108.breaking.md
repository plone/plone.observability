The root request span is now named after the HTTP method alone, for example
`GET`, instead of `GET <path>`. With the path in the name, every URL got its own
span name, and collectors that derive metrics from span names (the OpenTelemetry
Collector spanmetrics connector, the Tempo metrics generator) created one series
per URL: millions of series on a busy site. The path stays in the `url.path` or
`http.target` attribute of the span. The `ZPublisher.publish` span carries the
path in `url.path` instead of `http.route`, which must be low-cardinality. Update
dashboards and TraceQL queries that filter on the root span name or on
`http.route`.
