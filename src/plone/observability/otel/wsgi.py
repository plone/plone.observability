"""WSGI middleware + serving-only OTel activation via a PasteDeploy filter."""

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

from plone.observability.otel import catalog
from plone.observability.otel import provider
from plone.observability.otel import zodb


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter: activate tracing (serving only) and wrap the app."""
    if provider.is_enabled():
        provider.setup_tracing()
        zodb.register()
        catalog.instrument_catalog()
    return OpenTelemetryMiddleware(app)
