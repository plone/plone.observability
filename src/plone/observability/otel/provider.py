"""TracerProvider bootstrap and activation gating for the OTel extra."""

from plone.base.utils import boolean_value

import logging
import os


logger = logging.getLogger(__name__)

TRACER_NAME = "plone.observability"
_ACTIVE = False

# OTLP transports with a Python span exporter. The specification also defines
# http/json, which has none.
_PROTOCOLS = ("grpc", "http/protobuf")
_warned_protocol = False


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


def _otlp_protocol():
    """Return the OTLP transport for spans.

    The traces-specific variable wins over the general one, as the
    OpenTelemetry specification orders them. Without either, gRPC, which this
    package always used.
    """
    global _warned_protocol
    value = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL")
        or os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL")
        or "grpc"
    )
    value = value.strip().lower()
    if value in _PROTOCOLS:
        return value
    if not _warned_protocol:
        logger.warning(
            "Unsupported OTLP protocol %r for spans; using grpc. Supported: %s",
            value,
            ", ".join(_PROTOCOLS),
        )
        _warned_protocol = True
    return "grpc"


def _span_exporter():
    """Build the OTLP span exporter for the configured transport.

    The exporters read the endpoint variables themselves; the HTTP one appends
    ``/v1/traces`` to ``OTEL_EXPORTER_OTLP_ENDPOINT``.
    """
    if _otlp_protocol() == "http/protobuf":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
    return OTLPSpanExporter()


def setup_tracing():
    """Install a global TracerProvider with an OTLP exporter. Idempotent.

    Resource attributes (service.name etc.) and the OTLP endpoint are read
    from the standard OTEL_* env vars by the SDK/exporter themselves; the
    transport comes from OTEL_EXPORTER_OTLP_(TRACES_)PROTOCOL.
    """
    global _ACTIVE
    if _ACTIVE:
        return
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(BatchSpanProcessor(_span_exporter()))
    trace.set_tracer_provider(provider)
    _ACTIVE = True
