import resource

from zope.interface import implementer

from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric


@implementer(IMetricProvider)
class SystemMetricProvider:
    """Provides process-level system metrics (RSS, CPU)."""

    name = "system"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)

        # RSS in bytes. On Linux, ru_maxrss is in KB.
        rss_bytes = usage.ru_maxrss * 1024

        yield Metric(
            name="plone_process_rss_bytes",
            value=rss_bytes,
            type="gauge",
            scope="instance",
            help="Resident set size of the process in bytes",
        )

        cpu_seconds = usage.ru_utime + usage.ru_stime
        yield Metric(
            name="plone_process_cpu_seconds",
            value=round(cpu_seconds, 4),
            type="counter",
            scope="instance",
            help="Total CPU time (user + system) in seconds",
        )
