import threading
import time
from collections import defaultdict

from zope.interface import implementer

from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric

# Default histogram buckets (in seconds), matching Prometheus defaults
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class RequestTracker:
    """Thread-safe request statistics tracker."""

    def __init__(self, buckets=DEFAULT_BUCKETS):
        self._lock = threading.Lock()
        self.buckets = buckets
        self.request_count = 0
        self.duration_sum = 0.0
        self.bucket_counts = {b: 0 for b in buckets}
        self.bucket_counts[float("inf")] = 0
        self.error_counts = defaultdict(int)

    def record(self, duration, status_code):
        with self._lock:
            self.request_count += 1
            self.duration_sum += duration
            for bucket in self.buckets:
                if duration <= bucket:
                    self.bucket_counts[bucket] += 1
            self.bucket_counts[float("inf")] += 1
            if status_code >= 400:
                self.error_counts[status_code] += 1


# Module-level singleton, shared across requests
tracker = RequestTracker()


class ObservabilityMiddleware:
    """WSGI middleware that records request timing and status codes."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        start = time.time()
        status_code = 200

        def tracking_start_response(status, headers, exc_info=None):
            nonlocal status_code
            try:
                status_code = int(status.split(" ", 1)[0])
            except (ValueError, AttributeError):
                pass
            return start_response(status, headers, exc_info)

        try:
            result = self.app(environ, tracking_start_response)
            return result
        finally:
            duration = time.time() - start
            tracker.record(duration, status_code)


@implementer(IMetricProvider)
class RequestMetricProvider:
    """Provides request metrics from the WSGI middleware tracker."""

    name = "request"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        yield Metric(
            name="plone_requests_total",
            value=tracker.request_count,
            type="counter",
            scope="instance",
            help="Total number of HTTP requests",
        )

        yield Metric(
            name="plone_request_duration_seconds_sum",
            value=round(tracker.duration_sum, 4),
            type="counter",
            scope="instance",
            help="Total request duration in seconds",
        )

        yield Metric(
            name="plone_request_duration_seconds_count",
            value=tracker.request_count,
            type="counter",
            scope="instance",
            help="Total number of requests (histogram count)",
        )

        for bucket, count in sorted(tracker.bucket_counts.items()):
            le = "+Inf" if bucket == float("inf") else str(bucket)
            yield Metric(
                name="plone_request_duration_seconds_bucket",
                value=count,
                type="counter",
                scope="instance",
                help="Request duration histogram bucket",
                labels={"le": le},
            )

        for status_code, count in sorted(tracker.error_counts.items()):
            yield Metric(
                name="plone_request_errors",
                value=count,
                type="counter",
                scope="instance",
                help="Total HTTP errors by status code",
                labels={"status_code": str(status_code)},
            )


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter factory for WSGI middleware."""
    return ObservabilityMiddleware(app)
