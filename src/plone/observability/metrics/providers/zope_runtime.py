from importlib.metadata import distribution
from importlib.metadata import PackageNotFoundError
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import logging
import threading
import time


logger = logging.getLogger(__name__)

_start_time = time.time()


def _get_version(package_name, fallback="unknown"):
    try:
        return distribution(package_name).version
    except PackageNotFoundError:
        return fallback


@implementer(IMetricProvider)
class ZopeRuntimeMetricProvider:
    """Provides Zope runtime metrics: uptime, versions, threads."""

    name = "zope_runtime"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        yield Metric(
            name="plone_uptime_seconds",
            value=round(time.time() - _start_time, 2),
            type="gauge",
            scope="instance",
            help="Process uptime in seconds",
        )

        import sys

        yield Metric(
            name="plone_info",
            value=1,
            # Classic Prometheus text format (v0.0.4) has no "info" type; that
            # only exists in OpenMetrics. Use the conventional `*_info` gauge
            # (constant value 1, detail carried in labels), like python_info.
            type="gauge",
            scope="instance",
            help="Version information",
            labels={
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "zope_version": _get_version("Zope"),
                "plone_version": _get_version("Products.CMFPlone", "not installed"),
            },
        )

        active = threading.active_count()
        yield Metric(
            name="plone_threads_active",
            value=active,
            type="gauge",
            scope="instance",
            help="Number of active Python threads",
        )
