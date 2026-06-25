from collections import defaultdict
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import threading
import time


# Default histogram buckets (in seconds), matching Prometheus defaults
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


AUTH_CLASSES = ("authenticated", "anonymous")


class RequestTracker:
    """Thread-safe request statistics tracker, partitioned by auth class."""

    def __init__(self, buckets=DEFAULT_BUCKETS):
        self._lock = threading.Lock()
        self.buckets = buckets
        self._stats = {auth: self._new_stats() for auth in AUTH_CLASSES}

    def _new_stats(self):
        bucket_counts = dict.fromkeys(self.buckets, 0)
        bucket_counts[float("inf")] = 0
        return {
            "count": 0,
            "duration_sum": 0.0,
            "max_duration": 0.0,
            "buckets": bucket_counts,
            "errors": defaultdict(int),
        }

    def record(self, duration, status_code, authenticated=False):
        key = "authenticated" if authenticated else "anonymous"
        with self._lock:
            stats = self._stats[key]
            stats["count"] += 1
            stats["duration_sum"] += duration
            if duration > stats["max_duration"]:
                stats["max_duration"] = duration
            for bucket in self.buckets:
                if duration <= bucket:
                    stats["buckets"][bucket] += 1
            stats["buckets"][float("inf")] += 1
            if status_code >= 400:
                stats["errors"][status_code] += 1

    def stats_for(self, auth):
        return self._stats[auth]

    def take_max(self, auth):
        """Return the max duration observed since the last call and reset it.

        The max is a per-scrape-window gauge: a histogram cannot report the
        true maximum latency, so we track it directly and reset it on read so
        each scrape reflects the worst-case request in that window.
        """
        with self._lock:
            stats = self._stats[auth]
            value = stats["max_duration"]
            stats["max_duration"] = 0.0
            return value

    @property
    def request_count(self):
        return sum(s["count"] for s in self._stats.values())

    @property
    def duration_sum(self):
        return sum(s["duration_sum"] for s in self._stats.values())

    @property
    def error_counts(self):
        merged = defaultdict(int)
        for s in self._stats.values():
            for code, count in s["errors"].items():
                merged[code] += count
        return merged

    @property
    def bucket_counts(self):
        merged = {}
        for s in self._stats.values():
            for bucket, count in s["buckets"].items():
                merged[bucket] = merged.get(bucket, 0) + count
        return merged


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
            authenticated = bool(
                environ.get("plone.observability.authenticated", False)
            )
            tracker.record(duration, status_code, authenticated)


@implementer(IMetricProvider)
class RequestMetricProvider:
    """Provides request metrics from the WSGI middleware tracker."""

    name = "request"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        for auth in AUTH_CLASSES:
            stats = tracker.stats_for(auth)

            yield Metric(
                name="plone_requests_total",
                value=stats["count"],
                type="counter",
                scope="instance",
                help="Total number of HTTP requests",
                labels={"auth": auth},
            )

            yield Metric(
                name="plone_request_duration_seconds_sum",
                value=round(stats["duration_sum"], 4),
                type="counter",
                scope="instance",
                help="Total request duration in seconds",
                labels={"auth": auth},
            )

            yield Metric(
                name="plone_request_duration_seconds_count",
                value=stats["count"],
                type="counter",
                scope="instance",
                help="Total number of requests (histogram count)",
                labels={"auth": auth},
            )

            yield Metric(
                name="plone_request_duration_seconds_max",
                value=round(tracker.take_max(auth), 4),
                type="gauge",
                scope="instance",
                help=(
                    "Worst-case request duration in seconds since the last "
                    "scrape (the histogram cannot report the true maximum)"
                ),
                labels={"auth": auth},
            )

            for bucket, count in sorted(stats["buckets"].items()):
                le = "+Inf" if bucket == float("inf") else str(bucket)
                yield Metric(
                    name="plone_request_duration_seconds_bucket",
                    value=count,
                    type="counter",
                    scope="instance",
                    help="Request duration histogram bucket",
                    labels={"le": le, "auth": auth},
                )

            for status_code, count in sorted(stats["errors"].items()):
                yield Metric(
                    name="plone_request_errors",
                    value=count,
                    type="counter",
                    scope="instance",
                    help="Total HTTP errors by status code",
                    labels={"status_code": str(status_code), "auth": auth},
                )


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter factory for WSGI middleware."""
    return ObservabilityMiddleware(app)
