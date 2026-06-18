"""WSGI middleware that creates the root request span via OpenTelemetry."""

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter factory wrapping the app in the OTel WSGI middleware."""
    return OpenTelemetryMiddleware(app)
