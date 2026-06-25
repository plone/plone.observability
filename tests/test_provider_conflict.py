from plone.observability.interfaces import IMetricProvider
from ZODB.POSException import ConflictError
from ZODB.POSException import ReadConflictError
from zope.interface.verify import verifyObject


class FakeEvent:
    def __init__(self, exc, retry):
        self.exc_info = (type(exc), exc, None) if exc is not None else None
        self.retry = retry


def _reset():
    from plone.observability.metrics.providers import conflict

    conflict.tracker.counts.clear()
    return conflict


def test_tracker_records_by_retry():
    conflict = _reset()
    conflict.tracker.record(True)
    conflict.tracker.record(True)
    conflict.tracker.record(False)
    assert conflict.tracker.counts["true"] == 2
    assert conflict.tracker.counts["false"] == 1


def test_subscriber_counts_conflict_retry_true():
    conflict = _reset()
    conflict.on_pub_before_abort(FakeEvent(ConflictError(), retry=True))
    assert conflict.tracker.counts["true"] == 1
    assert conflict.tracker.counts["false"] == 0


def test_subscriber_counts_read_conflict_retry_false():
    conflict = _reset()
    conflict.on_pub_before_abort(FakeEvent(ReadConflictError(), retry=False))
    assert conflict.tracker.counts["false"] == 1


def test_subscriber_ignores_non_conflict():
    conflict = _reset()
    conflict.on_pub_before_abort(FakeEvent(ValueError("nope"), retry=True))
    assert conflict.tracker.counts == {}


def test_subscriber_tolerates_empty_exc_info():
    conflict = _reset()
    conflict.on_pub_before_abort(FakeEvent(None, retry=False))
    assert conflict.tracker.counts == {}


def test_provider_emits_both_series_as_counters():
    conflict = _reset()
    conflict.tracker.record(True)
    provider = conflict.ConflictMetricProvider(object())
    assert verifyObject(IMetricProvider, provider)
    metrics = {m.labels["retry"]: m for m in provider.collect()}
    assert set(metrics) == {"true", "false"}
    assert metrics["true"].name == "plone_zodb_conflicts_total"
    assert metrics["true"].type == "counter"
    assert metrics["true"].scope == "instance"
    assert metrics["true"].value == 1
    assert metrics["false"].value == 0
