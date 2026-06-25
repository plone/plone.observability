"""TracerProvider bootstrap and activation gating for the OTel extra."""

from plone.base.utils import boolean_value

import os


TRACER_NAME = "plone.observability"
_ACTIVE = False


def is_enabled():
    """Return whether tracing should be active.

    The master switch PLONE_OBSERVABILITY_OTEL_ENABLED wins when set to a
    recognized truthy/falsy value. Otherwise (unset/empty) tracing falls back to
    auto-activation when an OTLP endpoint is configured (the OTel convention).
    """
    auto = bool(
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    )
    return boolean_value(
        os.environ.get("PLONE_OBSERVABILITY_OTEL_ENABLED", ""),
        default=auto,
    )


def setup_tracing():
    """Install a global TracerProvider with an OTLP exporter. Idempotent.

    Resource attributes (service.name etc.) and the OTLP endpoint are read
    from the standard OTEL_* env vars by the SDK/exporter themselves.
    """
    global _ACTIVE
    if _ACTIVE:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _ACTIVE = True
