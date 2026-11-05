from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import logging
import os
import threading
import time


logger = logging.getLogger(__name__)


# ``@@metrics`` builds a fresh adapter per scrape, so the cache has to live at
# module level to survive between scrapes. Keyed by site id, so a site added
# within the TTL window shows up on the next scrape instead of after expiry.
_site_cache = {}  # site id -> (timestamp, [Metric, ...])
_site_cache_lock = threading.Lock()


def _cache_ttl():
    return int(os.environ.get("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "60"))


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


def _collect_site(site):
    """Collect the content metrics of one site from its catalog indexes."""
    catalog = site.unrestrictedTraverse("portal_catalog", None)
    if catalog is None:
        return []

    site_label = site.id
    metrics = []

    # Content counts by portal_type
    try:
        type_index = catalog.Indexes["portal_type"]
        for portal_type, count in type_index.uniqueValues(withLengths=True):
            metrics.append(
                Metric(
                    name="plone_content_total",
                    value=count,
                    type="gauge",
                    scope="global",
                    help="Number of content objects by portal type",
                    labels={"portal_type": portal_type, "site": site_label},
                )
            )
    except Exception:
        logger.debug(
            "portal_type index not available in %s (catalog is not "
            "ZCatalog-based); a catalog backend without the ZCatalog index "
            "API should replace the 'content' IMetricProvider adapter",
            site_label,
        )

    # Content counts by workflow state
    try:
        state_index = catalog.Indexes["review_state"]
        for state, count in state_index.uniqueValues(withLengths=True):
            metrics.append(
                Metric(
                    name="plone_content_by_state",
                    value=count,
                    type="gauge",
                    scope="global",
                    help="Number of content objects by workflow state",
                    labels={"state": state, "site": site_label},
                )
            )
    except Exception:
        logger.debug(
            "review_state index not available in %s (catalog is not ZCatalog-based)",
            site_label,
        )
    return metrics


@implementer(IMetricProvider)
class ContentMetricProvider:
    """Provides content count metrics from the portal catalog."""

    name = "content"
    scope = "global"

    def __init__(self, context):
        self.context = context

    def collect(self):
        sites = _find_plone_sites(self.context)
        now = time.time()
        ttl = _cache_ttl()
        for site in sites:
            site_id = site.id
            with _site_cache_lock:
                entry = _site_cache.get(site_id)
            if entry is not None and (now - entry[0]) < ttl:
                yield from entry[1]
                continue
            # Collect outside the lock so a slow catalog never serializes
            # concurrent scrapes behind it.
            metrics = _collect_site(site)
            with _site_cache_lock:
                _site_cache[site_id] = (now, metrics)
            yield from metrics

        # Drop entries of sites that no longer exist.
        current = {site.id for site in sites}
        with _site_cache_lock:
            for site_id in set(_site_cache) - current:
                del _site_cache[site_id]
