import logging

from Products.Five import BrowserView
from zope.component import getAdapters, queryUtility

from plone.observability.interfaces import IMetricFormatter, IMetricProvider
from plone.observability.metrics.access import is_allowed

logger = logging.getLogger(__name__)


class MetricsView(BrowserView):
    """@@metrics endpoint serving collected metrics in configurable formats."""

    def __call__(self):
        # Check IP access
        peer_ip = self.request.environ.get("REMOTE_ADDR", "")
        headers = {
            "X-Forwarded-For": self.request.getHeader("X-Forwarded-For", ""),
        }
        if not is_allowed(peer_ip, headers):
            self.request.response.setStatus(403)
            return "Forbidden"

        # Select formatter
        formatter = self._get_formatter()
        if formatter is None:
            self.request.response.setStatus(500)
            return "No metric formatter available"

        # Collect metrics from all providers
        metrics = []
        for name, provider in getAdapters((self.context,), IMetricProvider):
            try:
                metrics.extend(provider.collect())
            except Exception:
                logger.exception("Error collecting metrics from provider %s", name)

        # Format and return
        self.request.response.setHeader("Content-Type", formatter.content_type)
        return formatter.format(metrics)

    def _get_formatter(self):
        # Query parameter takes precedence
        format_name = self.request.get("format", None)
        if format_name:
            formatter = queryUtility(IMetricFormatter, name=format_name)
            if formatter is not None:
                return formatter

        # Check Accept header
        accept = self.request.getHeader("Accept", "")
        if "application/json" in accept:
            formatter = queryUtility(IMetricFormatter, name="json")
            if formatter is not None:
                return formatter

        # Default to prometheus
        return queryUtility(IMetricFormatter, name="prometheus")
