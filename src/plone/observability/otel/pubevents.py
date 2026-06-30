"""ZPublisher pubevent subscribers producing a publishing span per request.

The span starts on IPubStart, is attributed on IPubAfterTraversal, and ends on
IPubSuccess/IPubFailure. It is stashed on request.environ because start and end
happen in different subscribers. Catalog and commit spans (started elsewhere
during the request) nest under it because it is made the current context.
"""

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import set_span_in_context
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode
from plone.base.utils import boolean_value
from plone.observability.auth import get_auth_info
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME

import logging
import os


logger = logging.getLogger(__name__)


def _user_id_enabled():
    return boolean_value(
        os.environ.get("PLONE_OBSERVABILITY_OTEL_USER_ID", ""), default=False
    )


_SPAN_KEY = "plone.observability.otel.publish_span"
_TOKEN_KEY = "plone.observability.otel.publish_token"


def on_pub_start(event):
    if not is_enabled():
        return
    if exclusions.is_excluded(event.request.get("PATH_INFO", "")):
        # Excluded path: emit no publish span, and mark the request suppressed so
        # the catalog/zodb/transformchain subscribers skip their spans too (they
        # would otherwise be exported as root spans). Detached in _finish.
        event.request.environ[_TOKEN_KEY] = exclusions.suppress_token()
        return
    tracer = trace.get_tracer(TRACER_NAME)
    span = tracer.start_span("ZPublisher.publish")
    token = otel_context.attach(set_span_in_context(span))
    event.request.environ[_SPAN_KEY] = span
    event.request.environ[_TOKEN_KEY] = token


def on_after_traversal(event):
    span = event.request.environ.get(_SPAN_KEY)
    if span is None:
        return
    span.set_attribute("http.route", event.request.get("PATH_INFO", ""))
    published = event.request.get("PUBLISHED", None)
    if published is not None:
        span.set_attribute("plone.published", type(published).__name__)


def _finish(request, error=None):
    span = request.environ.pop(_SPAN_KEY, None)
    token = request.environ.pop(_TOKEN_KEY, None)
    if token is not None:
        otel_context.detach(token)
    if span is None:
        return
    authenticated, user_id = get_auth_info()
    span.set_attribute("enduser.authenticated", authenticated)
    if authenticated and user_id and _user_id_enabled():
        span.set_attribute("enduser.id", str(user_id))
    if error is not None:
        span.set_status(Status(StatusCode.ERROR))
        span.record_exception(error)
    span.end()


def on_pub_success(event):
    _finish(event.request)


def on_pub_failure(event):
    error = event.exc_info[1] if event.exc_info else None
    _finish(event.request, error=error)
