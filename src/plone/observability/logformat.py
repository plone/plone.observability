"""Log formatter that writes the current trace and span IDs into log lines.

Set it as the ``class`` of a ``logging.config.fileConfig`` formatter, such as
the ``[formatter_*]`` sections of ``wsgi.ini``, and use ``%(otelTraceID)s``
and ``%(otelSpanID)s`` in its ``format``. These are the attribute names
``opentelemetry-instrumentation-logging`` sets, so a format works with both.

The IDs are read when a record is formatted, not when it is created. A format
using them therefore works from the first log line on: ``fileConfig`` builds
the formatter before PasteDeploy loads the ``opentelemetry`` filter and before
Zope starts. Handlers that write directly, such as stream and file handlers,
format in the thread that logs, so a record logged during a request gets that
request's span. Outside a span, and without the ``[opentelemetry]`` extra,
both IDs are ``0``.
"""

import logging


try:
    from opentelemetry import trace as _trace
except ImportError:  # extra not installed
    _trace = None

INVALID_ID = "0"


class TraceContextFormatter(logging.Formatter):
    """Formatter that sets ``otelTraceID`` and ``otelSpanID`` on each record."""

    def format(self, record):
        record.otelTraceID = record.otelSpanID = INVALID_ID
        if _trace is not None:
            context = _trace.get_current_span().get_span_context()
            if context.is_valid:
                record.otelTraceID = _trace.format_trace_id(context.trace_id)
                record.otelSpanID = _trace.format_span_id(context.span_id)
        return super().format(record)
