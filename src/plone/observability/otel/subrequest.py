"""Span per plone.subrequest call, so blocks/mosaic tiles show in the trace.

plone.subrequest bypasses ZPublisher.publish and the WSGI server, so neither the
WSGI middleware nor the pubevent subscribers see it, and there is no subrequest
event to hook. We wrap the function (see register()). Each subrequest becomes a
span nested under the active transform span (the tiles transform), else under
the current context (the publish span).
"""

from opentelemetry import trace
from opentelemetry.trace import set_span_in_context
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode
from plone.observability.otel import dbcounts
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME
from plone.observability.otel.transformchain import _SINGLE_SPAN_KEY
from urllib.parse import urlsplit
from zope.globalrequest import getRequest

import wrapt


_TARGET_MODULES = ("plone.app.blocks.utils", "plone.subrequest")
_registered = False


def _span_name(url):
    path = urlsplit(url or "").path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else ""
    return f"subrequest {segment}" if segment else "subrequest"


def _parent_context(request):
    """Context nesting the span under the active transform span, else current."""
    if request is not None:
        try:
            span = request.environ.get(_SINGLE_SPAN_KEY)
        except Exception:
            span = None
        if span is not None:
            return set_span_in_context(span)
    return None  # None -> start_as_current_span uses the current context


def _traced_subrequest(wrapped, instance, args, kwargs):
    if not is_enabled() or exclusions.is_suppressed():
        return wrapped(*args, **kwargs)
    url = args[0] if args else kwargs.get("url", "")
    request = getRequest()
    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(
        _span_name(url), context=_parent_context(request)
    ) as span:
        span.set_attribute("http.url", url)
        span.set_attribute("http.method", "GET")
        before = dbcounts.read_counts(request)
        try:
            response = wrapped(*args, **kwargs)
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(exc)
            raise
        dbcounts.annotate(span, before, dbcounts.read_counts(request))
        status = getattr(response, "status", None)
        if isinstance(status, int):
            span.set_attribute("http.status_code", status)
        return response


def register():
    """Wrap subrequest() in its caller modules via post-import hooks. Idempotent.

    Targets modules by name so this is safe even when plone.subrequest /
    plone.app.blocks are absent: the hooks stay inert until those modules import.
    """
    global _registered
    if _registered:
        return

    def _patch(module):
        try:
            wrapt.wrap_function_wrapper(module, "subrequest", _traced_subrequest)
        except Exception:
            # Module present but no subrequest attr (API drift) -- skip silently.
            pass

    for name in _TARGET_MODULES:
        wrapt.register_post_import_hook(_patch, name)
    _registered = True
