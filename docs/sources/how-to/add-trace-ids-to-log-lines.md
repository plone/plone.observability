# How to add trace IDs to log lines

This guide shows you how to write the trace ID of the current request into every log line.
Use it to go from a trace to the log lines of the same request.
Your log store then finds them with a search for the trace ID.

For the formatter and the attributes it sets, see {ref}`tracing-log-formatter`.

(add-trace-ids-to-log-lines-use-the-formatter)=

## Use the formatter

Set `TraceContextFormatter` as the class of the formatters in the logging part of your `wsgi.ini`.
Add `%(otelTraceID)s` to their format, and `%(otelSpanID)s` if you also want the span.

```ini
[formatter_generic]
class = plone.observability.logformat.TraceContextFormatter
format = %(asctime)s %(levelname)-7.7s [%(name)s:%(lineno)s][%(threadName)s] trace_id=%(otelTraceID)s %(message)s

[formatter_message]
class = plone.observability.logformat.TraceContextFormatter
format = %(message)s trace_id=%(otelTraceID)s
```

`generic` formats the event log and the console.
`message` formats the access log that `translogger` writes.
The ID goes at the end of the access log line, where it does not disturb parsers of the combined log format.

(add-trace-ids-to-log-lines-with-plone-recipe-zope2instance)=

## With plone.recipe.zope2instance

The recipe writes `wsgi.ini` again at each buildout run.
Copy the logging part of its default template into your project, for example as `templates/wsgi-logging.ini`.
The recipe keeps that part in `default_wsgi_logging_ini_template`, in `plone/recipe/zope2instance/recipe.py`.
Change the two formatters in your copy, then point the recipe at it.

```ini
[instance]
recipe = plone.recipe.zope2instance
wsgi-logging-ini-template = ${buildout:directory}/templates/wsgi-logging.ini
```

The recipe fills the template with Python `%` formatting.
Write each `%` of a log format as `%%`, as the default template does.

```ini
[formatter_generic]
class = plone.observability.logformat.TraceContextFormatter
format = %%(asctime)s %%(levelname)-7.7s [%%(name)s:%%(lineno)s][%%(threadName)s] trace_id=%%(otelTraceID)s %%(message)s

[formatter_message]
class = plone.observability.logformat.TraceContextFormatter
format = %%(message)s trace_id=%%(otelTraceID)s
```

(add-trace-ids-to-log-lines-read-the-ids)=

## Read the IDs

A trace ID has 32 hexadecimal characters and a span ID has 16, as your trace backend shows them.
Both are `0` for a line logged outside a span.
This is the case at startup, for excluded URLs such as the `@@metrics` scrape, and when tracing is off.

The formatter reads the IDs when it formats a line.
A format that uses them works from the first log line on, before the `opentelemetry` filter loads.
It also works without the `opentelemetry` extra.

(add-trace-ids-to-log-lines-find-the-log-lines-of-a-trace)=

## Find the log lines of a trace

Search your log store for the trace ID as a quoted string, for example `"4bf92f3577b34da6a3ce929d0e0e4736"`.
The trace ID alone identifies the request.
Leave out filters on fields that only spans carry, such as `service.name`.

In Grafana, the link from a span to its logs comes from the "Trace to logs" setting of the Tempo data source.
Turn on "Filter by trace ID".
Remove the default `service.name` tag unless your log records carry that field.

```{seealso}
- {ref}`tracing-log-formatter` for the formatter and the attributes it sets.
- {doc}`/how-to/enable-opentelemetry-tracing` to turn tracing on.
```
