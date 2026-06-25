from collections import defaultdict
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from ZODB.POSException import ConflictError
from zope.interface import implementer

import threading


class ConflictTracker:
    """Thread-safe ZODB conflict counter, partitioned by retry outcome."""

    def __init__(self):
        self._lock = threading.Lock()
        self.counts = defaultdict(int)  # {"true"|"false": int}

    def record(self, retry):
        key = "true" if retry else "false"
        with self._lock:
            self.counts[key] += 1


tracker = ConflictTracker()


def on_pub_before_abort(event):
    """IPubBeforeAbort subscriber: count ConflictErrors, labelled by retry."""
    exc = event.exc_info[1] if event.exc_info else None
    if isinstance(exc, ConflictError):
        tracker.record(bool(event.retry))


@implementer(IMetricProvider)
class ConflictMetricProvider:
    """Provides ZODB conflict metrics from the pubevent tracker."""

    name = "conflict"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        for retry in ("true", "false"):
            yield Metric(
                name="plone_zodb_conflicts_total",
                value=tracker.counts[retry],
                type="counter",
                scope="instance",
                help=(
                    "ZODB conflict errors during publish "
                    "(retry=true was retried, retry=false gave up)"
                ),
                labels={"retry": retry},
            )
