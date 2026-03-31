from plone.observability.metric import Metric


def test_metric_creation():
    m = Metric(
        name="plone_uptime_seconds",
        value=1234.5,
        type="gauge",
        scope="instance",
        help="Uptime in seconds",
        labels={},
    )
    assert m.name == "plone_uptime_seconds"
    assert m.value == 1234.5
    assert m.type == "gauge"
    assert m.scope == "instance"
    assert m.help == "Uptime in seconds"
    assert m.labels == {}


def test_metric_with_labels():
    m = Metric(
        name="plone_content_total",
        value=42,
        type="gauge",
        scope="global",
        help="Content count by type",
        labels={"portal_type": "Document"},
    )
    assert m.labels == {"portal_type": "Document"}
    assert m.scope == "global"


def test_metric_default_labels():
    m = Metric(
        name="plone_test",
        value=1,
        type="gauge",
        scope="instance",
        help="Test",
    )
    assert m.labels == {}
