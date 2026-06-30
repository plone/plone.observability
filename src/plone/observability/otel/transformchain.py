"""plone.transformchain span instrumentation via its before/after events.

`plone.transformchain` fires BeforeTransforms/AfterTransforms around the whole
chain and BeforeSingleTransform/AfterSingleTransform around each transform. We
turn those into a ``transformchain`` parent span with one ``transform.<name>``
child per transform -- no monkeypatching.

The child spans are parented explicitly on the chain span rather than attached
to the global OTel context, so there are no context tokens that could leak. The
chain span itself is a child of the current context, which during a request is
the ``ZPublisher.publish`` span (the chain runs on IPubBeforeCommit).

Spans are stashed on ``request.environ`` because start and end happen in
different subscribers. ``Transformer.__call__`` swallows transform exceptions
(except ConflictError) and returns without firing AfterTransforms, so a
request-end flush closes any spans left dangling.
"""

from opentelemetry import trace
from opentelemetry.trace import set_span_in_context
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME


_CHAIN_SPAN_KEY = "plone.observability.otel.transformchain_span"
_CHAIN_COUNT_KEY = "plone.observability.otel.transformchain_count"
_SINGLE_SPAN_KEY = "plone.observability.otel.transform_span"


def on_before_transforms(event):
    if not is_enabled() or exclusions.is_suppressed():
        return
    tracer = trace.get_tracer(TRACER_NAME)
    # Child of the current context -- the publish span during a request.
    span = tracer.start_span("transformchain")
    event.request.environ[_CHAIN_SPAN_KEY] = span
    event.request.environ[_CHAIN_COUNT_KEY] = 0


def on_before_single_transform(event):
    chain = event.request.environ.get(_CHAIN_SPAN_KEY)
    if chain is None:
        return
    tracer = trace.get_tracer(TRACER_NAME)
    span = tracer.start_span(
        f"transform.{event.name}",
        context=set_span_in_context(chain),
    )
    span.set_attribute("plone.transform.name", event.name)
    span.set_attribute("plone.transform.handler", type(event.handler).__name__)
    event.request.environ[_SINGLE_SPAN_KEY] = span
    event.request.environ[_CHAIN_COUNT_KEY] = (
        event.request.environ.get(_CHAIN_COUNT_KEY, 0) + 1
    )


def on_after_single_transform(event):
    span = event.request.environ.pop(_SINGLE_SPAN_KEY, None)
    if span is not None:
        span.end()


def on_after_transforms(event):
    _finish(event.request)


def _finish(request):
    """End any open transformchain spans stashed on the request.

    Idempotent: a normal AfterTransforms finish leaves nothing for the
    request-end flush to do, and vice versa.
    """
    single = request.environ.pop(_SINGLE_SPAN_KEY, None)
    if single is not None:
        single.end()
    span = request.environ.pop(_CHAIN_SPAN_KEY, None)
    if span is None:
        request.environ.pop(_CHAIN_COUNT_KEY, None)
        return
    count = request.environ.pop(_CHAIN_COUNT_KEY, 0)
    span.set_attribute("plone.transformchain.transform_count", count)
    span.end()


def on_pub_success(event):
    _finish(event.request)


def on_pub_failure(event):
    _finish(event.request)
