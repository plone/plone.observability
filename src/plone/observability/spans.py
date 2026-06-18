"""Public, dependency-optional tracing helper.

`start_span` is safe to call whether or not the [opentelemetry] extra is
installed. Without OpenTelemetry it is a no-op context manager yielding None.
"""

from contextlib import contextmanager


try:
    from opentelemetry import trace as _trace
except ImportError:  # extra not installed
    _trace = None

TRACER_NAME = "plone.observability"


@contextmanager
def start_span(name, attributes=None):
    """Start a child span of the current context.

    Yields the span, or None when OpenTelemetry is not installed.
    """
    if _trace is None:
        yield None
        return
    tracer = _trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            span.set_attributes(attributes)
        yield span
