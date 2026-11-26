Add `plone.observability.logformat.TraceContextFormatter`, a log formatter that
writes the trace and span IDs of the current request into log lines. Set it as
the `class` of the formatters in `wsgi.ini` and use `%(otelTraceID)s` and
`%(otelSpanID)s` in their format. A search for a trace ID then finds the access
line and the event log lines of that request. The IDs are read when a line is
formatted: the format works from the first startup line on, with tracing off, and
without the `opentelemetry` extra. Outside a span both IDs are `0`.
