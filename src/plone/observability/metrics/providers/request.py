from collections import defaultdict
from plone.observability import rss
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import logging
import threading
import time


logger = logging.getLogger(__name__)


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


# RSS growth per request, in bytes. Growth only: a negative observation would
# make the histogram's _sum decrease, which a counter must not do.
RSS_GROWTH_BUCKETS = (
    0,
    64 * 1024,
    256 * 1024,
    1024**2,
    4 * 1024**2,
    16 * 1024**2,
    64 * 1024**2,
    256 * 1024**2,
)


class RSSGrowthTracker:
    """Thread-safe histogram of the RSS growth per request."""

    def __init__(self, buckets=RSS_GROWTH_BUCKETS):
        self._lock = threading.Lock()
        self.buckets = buckets
        self.counts = [0] * (len(buckets) + 1)  # the last one is +Inf
        self.count = 0
        self.total = 0

    def record(self, growth):
        with self._lock:
            for i, bound in enumerate(self.buckets):
                if growth <= bound:
                    self.counts[i] += 1
            self.counts[-1] += 1
            self.count += 1
            self.total += growth

    def snapshot(self):
        with self._lock:
            return list(self.counts), self.count, self.total


rss_tracker = RSSGrowthTracker()


def _record_rss_growth(environ, start, end):
    if start is None or end is None:
        return
    growth = max(end - start, 0)
    rss_tracker.record(growth)
    threshold = rss.warn_threshold_bytes()
    if threshold and growth >= threshold:
        # The path only: query strings can carry tokens (password reset).
        logger.warning(
            "Request grew the process RSS by %.1f MiB: %s %s",
            growth / rss.MiB,
            environ.get("REQUEST_METHOD", ""),
            environ.get("PATH_INFO", ""),
        )


class ObservabilityMiddleware:
    """WSGI middleware that records request timing and status codes."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        start = time.time()
        rss_enabled = rss.enabled()
        rss_start = rss.read() if rss_enabled else None
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
            if rss_enabled:
                _record_rss_growth(environ, rss_start, rss.read())


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

        if rss.enabled():
            yield from self._rss_growth()

    def _rss_growth(self):
        counts, count, total = rss_tracker.snapshot()
        yield Metric(
            name="plone_request_rss_growth_bytes_sum",
            value=total,
            type="counter",
            scope="instance",
            help="Total growth of the process RSS during requests in bytes",
        )
        yield Metric(
            name="plone_request_rss_growth_bytes_count",
            value=count,
            type="counter",
            scope="instance",
            help="Number of requests with an RSS reading (histogram count)",
        )
        bounds = [str(bound) for bound in rss_tracker.buckets] + ["+Inf"]
        for le, bucket_count in zip(bounds, counts, strict=True):
            yield Metric(
                name="plone_request_rss_growth_bytes_bucket",
                value=bucket_count,
                type="counter",
                scope="instance",
                help="RSS growth per request histogram bucket",
                labels={"le": le},
            )


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter factory for WSGI middleware."""
    return ObservabilityMiddleware(app)
