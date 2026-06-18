"""Activate tracing components at process start when enabled."""

import logging

from plone.observability.otel import catalog
from plone.observability.otel import provider
from plone.observability.otel import zodb


logger = logging.getLogger(__name__)


def on_process_starting(event):
    if not provider.is_enabled():
        return
    logger.info("Activating plone.observability OpenTelemetry tracing")
    provider.setup_tracing()
    zodb.register()
    catalog.instrument_catalog()
