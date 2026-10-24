from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import os
import resource
import sys


_STATM = "/proc/self/statm"


def _current_rss_bytes():
    """Return the current resident set size in bytes, or None without /proc.

    The second field of ``/proc/self/statm`` is the number of resident pages.
    """
    try:
        with open(_STATM) as f:
            resident_pages = int(f.read().split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return resident_pages * os.sysconf("SC_PAGE_SIZE")


@implementer(IMetricProvider)
class SystemMetricProvider:
    """Provides process-level system metrics (RSS, CPU)."""

    name = "system"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)

        # Only Linux exposes the current RSS without extra dependencies. Where
        # it is unavailable we leave the metric out rather than report the
        # peak under this name.
        rss_bytes = _current_rss_bytes()
        if rss_bytes is not None:
            yield Metric(
                name="plone_process_rss_bytes",
                value=rss_bytes,
                type="gauge",
                scope="instance",
                help="Current resident set size of the process in bytes",
            )

        # ru_maxrss is the peak RSS: in bytes on macOS, in KiB elsewhere.
        peak_bytes = usage.ru_maxrss
        if sys.platform != "darwin":
            peak_bytes *= 1024
        yield Metric(
            name="plone_process_rss_peak_bytes",
            value=peak_bytes,
            type="gauge",
            scope="instance",
            help="Peak resident set size of the process in bytes",
        )

        cpu_seconds = usage.ru_utime + usage.ru_stime
        yield Metric(
            name="plone_process_cpu_seconds",
            value=round(cpu_seconds, 4),
            type="counter",
            scope="instance",
            help="Total CPU time (user + system) in seconds",
        )
