"""WSGI middleware + serving-only OTel activation via a PasteDeploy filter."""

from opentelemetry import trace
from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
from plone.observability import rss
from plone.observability.otel import catalog
from plone.observability.otel import exclusions
from plone.observability.otel import instrumentors
from plone.observability.otel import provider
from plone.observability.otel import rendering
from plone.observability.otel import subrequest
from plone.observability.otel import zodb


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter: activate tracing (serving only) and wrap the app.

    The bare ``OpenTelemetryMiddleware`` has no excluded-URL support, so we wrap
    it with a path check: excluded requests (e.g. the ``@@metrics`` scrape) skip
    the middleware entirely and get no WSGI server span.
    """
    if provider.is_enabled():
        provider.setup_tracing()
        zodb.register()
        catalog.instrument_catalog()
        subrequest.register()
        rendering.register()
        instrumentors.enable()

    def rss_app(environ, start_response):
        # Runs inside the server span, so the attributes land on it.
        if not rss.enabled():
            return app(environ, start_response)
        start = rss.read()
        try:
            return app(environ, start_response)
        finally:
            rss.annotate(trace.get_current_span(), start, rss.read())

    traced_app = OpenTelemetryMiddleware(rss_app)

    def filtered(environ, start_response):
        if exclusions.is_excluded(environ.get("PATH_INFO", "")):
            return app(environ, start_response)
        return traced_app(environ, start_response)

    return filtered
