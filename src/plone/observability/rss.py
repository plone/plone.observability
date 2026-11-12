"""Opt-in RSS growth per request and per tile subrequest (#94).

Shared by the metrics middleware (histogram, warning) and the OpenTelemetry
spans (attributes). RSS is process-wide and counts pages, not allocations:
concurrent requests show up in each other's readings, and a request served
from memory the allocator already holds reads as zero growth.
"""

from plone.observability.metrics.providers.system import _current_rss_bytes
from plone.observability.utils import boolean_value

import os


START_ATTR = "plone.process.rss_start_bytes"
END_ATTR = "plone.process.rss_end_bytes"
DELTA_ATTR = "plone.process.rss_delta_bytes"

MiB = 1024 * 1024


def enabled():
    return boolean_value(os.environ.get("PLONE_OBSERVABILITY_REQUEST_RSS", "0"))


def warn_threshold_bytes():
    """Growth that logs a warning; 0 disables it."""
    return int(os.environ.get("PLONE_OBSERVABILITY_REQUEST_RSS_WARN_MIB", "20")) * MiB


def read():
    """Current RSS in bytes, or None without ``/proc``."""
    return _current_rss_bytes()


def annotate(span, start, end):
    """Record the readings on *span*; the delta keeps its sign there."""
    if start is None or end is None:
        return
    span.set_attribute(START_ATTR, start)
    span.set_attribute(END_ATTR, end)
    span.set_attribute(DELTA_ATTR, end - start)
