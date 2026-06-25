from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.request import RequestMetricProvider
from plone.observability.metrics.providers.request import RequestTracker
from zope.interface.verify import verifyObject

import threading


class FakeApp:
    pass


class TestRequestTracker:
    def test_record_increments_count(self):
        tracker = RequestTracker()
        tracker.record(0.1, 200)
        tracker.record(0.2, 200)
        assert tracker.request_count == 2

    def test_record_tracks_errors(self):
        tracker = RequestTracker()
        tracker.record(0.1, 500)
        tracker.record(0.2, 503)
        tracker.record(0.3, 200)
        assert tracker.error_counts[500] == 1
        assert tracker.error_counts[503] == 1

    def test_record_updates_duration_buckets(self):
        tracker = RequestTracker()
        tracker.record(0.001, 200)
        tracker.record(0.1, 200)
        tracker.record(5.0, 200)
        assert tracker.duration_sum > 0
        assert tracker.request_count == 3

    def test_record_tracks_max_duration(self):
        tracker = RequestTracker()
        tracker.record(0.1, 200)
        tracker.record(0.5, 200)
        tracker.record(0.3, 200)
        assert tracker.stats_for("anonymous")["max_duration"] == 0.5

    def test_max_duration_is_per_auth(self):
        tracker = RequestTracker()
        tracker.record(0.2, 200, authenticated=True)
        tracker.record(0.9, 200, authenticated=False)
        assert tracker.stats_for("authenticated")["max_duration"] == 0.2
        assert tracker.stats_for("anonymous")["max_duration"] == 0.9

    def test_take_max_returns_and_resets(self):
        tracker = RequestTracker()
        tracker.record(0.4, 200)
        tracker.record(0.7, 200)
        assert tracker.take_max("anonymous") == 0.7
        # window reset: no requests since -> max is back to zero
        assert tracker.take_max("anonymous") == 0.0
        # a new request opens a fresh window
        tracker.record(0.2, 200)
        assert tracker.take_max("anonymous") == 0.2

    def test_record_separates_by_auth(self):
        tracker = RequestTracker()
        tracker.record(0.1, 200, authenticated=True)
        tracker.record(0.2, 200, authenticated=False)
        tracker.record(0.3, 500, authenticated=True)
        assert tracker.stats_for("authenticated")["count"] == 2
        assert tracker.stats_for("anonymous")["count"] == 1
        assert tracker.stats_for("authenticated")["errors"][500] == 1
        assert tracker.stats_for("anonymous")["errors"] == {}

    def test_aggregate_properties_sum_both_classes(self):
        tracker = RequestTracker()
        tracker.record(0.1, 200, authenticated=True)
        tracker.record(0.2, 503, authenticated=False)
        assert tracker.request_count == 2
        assert tracker.error_counts[503] == 1
        assert tracker.duration_sum > 0

    def test_thread_safety(self):
        tracker = RequestTracker()
        errors = []

        def record_many():
            try:
                for _ in range(100):
                    tracker.record(0.01, 200)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert tracker.request_count == 1000


class TestMiddlewareAuth:
    def _run(self, environ):
        from plone.observability.metrics.providers.request import (
            ObservabilityMiddleware,
        )
        from plone.observability.metrics.providers.request import tracker

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b""]

        before = tracker.stats_for("authenticated")["count"]
        ObservabilityMiddleware(app)(environ, lambda s, h, e=None: None)
        after = tracker.stats_for("authenticated")["count"]
        return after - before

    def test_authenticated_request_recorded_as_authenticated(self):
        delta = self._run({"plone.observability.authenticated": True})
        assert delta == 1

    def test_request_without_flag_is_anonymous(self):
        delta = self._run({})
        assert delta == 0


class TestProviderAuthLabel:
    def test_all_request_metrics_carry_auth_label(self):
        from plone.observability.metrics.providers.request import RequestMetricProvider
        from plone.observability.metrics.providers.request import tracker

        tracker.record(0.1, 200, authenticated=True)
        tracker.record(0.2, 500, authenticated=False)

        metrics = list(RequestMetricProvider(FakeApp()).collect())
        totals = [m for m in metrics if m.name == "plone_requests_total"]
        auth_values = {m.labels["auth"] for m in totals}
        assert auth_values == {"authenticated", "anonymous"}

        errors = [m for m in metrics if m.name == "plone_request_errors"]
        assert all("auth" in m.labels for m in errors)
        buckets = [
            m for m in metrics if m.name == "plone_request_duration_seconds_bucket"
        ]
        assert all("auth" in m.labels and "le" in m.labels for m in buckets)


class TestRequestMetricProvider:
    def test_implements_interface(self):
        provider = RequestMetricProvider(FakeApp())
        assert verifyObject(IMetricProvider, provider)

    def test_scope_is_instance(self):
        provider = RequestMetricProvider(FakeApp())
        assert provider.scope == "instance"

    def test_collects_request_count(self):
        provider = RequestMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_requests_total" in metrics

    def test_collects_duration_histogram(self):
        provider = RequestMetricProvider(FakeApp())
        metrics = list(provider.collect())
        bucket_metrics = [
            m for m in metrics if m.name == "plone_request_duration_seconds_bucket"
        ]
        assert len(bucket_metrics) > 0

    def test_collects_max_duration_gauge(self):
        from plone.observability.metrics.providers.request import tracker

        tracker.record(0.42, 200, authenticated=False)
        provider = RequestMetricProvider(FakeApp())
        metrics = list(provider.collect())
        maxima = {
            m.labels["auth"]: m
            for m in metrics
            if m.name == "plone_request_duration_seconds_max"
        }
        assert set(maxima) == {"authenticated", "anonymous"}
        assert maxima["anonymous"].type == "gauge"
        assert maxima["anonymous"].value == 0.42

    def test_max_duration_gauge_resets_each_scrape(self):
        from plone.observability.metrics.providers.request import tracker

        tracker.record(0.42, 200, authenticated=False)
        provider = RequestMetricProvider(FakeApp())

        def anon_max(metrics):
            return next(
                m.value
                for m in metrics
                if m.name == "plone_request_duration_seconds_max"
                and m.labels["auth"] == "anonymous"
            )

        assert anon_max(list(provider.collect())) == 0.42
        # second scrape with no new requests -> window is empty again
        assert anon_max(list(provider.collect())) == 0.0
