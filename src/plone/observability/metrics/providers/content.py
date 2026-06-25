import logging
import os
import time

from zope.interface import implementer

from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric

logger = logging.getLogger(__name__)


def _find_plone_sites(app):
    """Find IPloneSiteRoot objects in the app root."""
    try:
        from Products.CMFPlone.interfaces import IPloneSiteRoot
    except ImportError:
        return []

    sites = []
    for obj in app.objectValues():
        if IPloneSiteRoot.providedBy(obj):
            sites.append(obj)
    return sites


@implementer(IMetricProvider)
class ContentMetricProvider:
    """Provides content count metrics from the portal catalog."""

    name = "content"
    scope = "global"

    def __init__(self, context):
        self.context = context
        self._cache = None
        self._cache_time = 0

    def _get_ttl(self):
        return int(os.environ.get("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "60"))

    def collect(self):
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self._get_ttl():
            yield from self._cache
            return

        metrics = list(self._collect_fresh())
        self._cache = metrics
        self._cache_time = now
        yield from metrics

    def _collect_fresh(self):
        sites = _find_plone_sites(self.context)
        for site in sites:
            catalog = site.unrestrictedTraverse("portal_catalog", None)
            if catalog is None:
                continue

            site_label = site.id

            # Content counts by portal_type
            try:
                type_index = catalog.Indexes["portal_type"]
                for portal_type, count in type_index.uniqueValues(withLengths=True):
                    yield Metric(
                        name="plone_content_total",
                        value=count,
                        type="gauge",
                        scope="global",
                        help="Number of content objects by portal type",
                        labels={"portal_type": portal_type, "site": site_label},
                    )
            except Exception:
                logger.debug(
                    "portal_type index not available in %s (catalog is not "
                    "ZCatalog-based); a backend-specific provider should supply "
                    "content metrics",
                    site_label,
                )

            # Content counts by workflow state
            try:
                state_index = catalog.Indexes["review_state"]
                for state, count in state_index.uniqueValues(withLengths=True):
                    yield Metric(
                        name="plone_content_by_state",
                        value=count,
                        type="gauge",
                        scope="global",
                        help="Number of content objects by workflow state",
                        labels={"state": state, "site": site_label},
                    )
            except Exception:
                logger.debug(
                    "review_state index not available in %s (catalog is not "
                    "ZCatalog-based)",
                    site_label,
                )
