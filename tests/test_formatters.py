from plone.observability.metric import Metric
from plone.observability.metrics.formatters import JSONFormatter
from plone.observability.metrics.formatters import PrometheusFormatter


class TestPrometheusFormatter:
    def test_format_gauge(self):
        formatter = PrometheusFormatter()
        metrics = [
            Metric(
                name="plone_uptime_seconds",
                value=1234.5,
                type="gauge",
                scope="instance",
                help="Uptime in seconds",
            ),
        ]
        result = formatter.format(metrics)
        assert "# HELP plone_uptime_seconds Uptime in seconds" in result
        assert "# TYPE plone_uptime_seconds gauge" in result
        assert 'plone_uptime_seconds{scope="instance"} 1234.5' in result

    def test_format_with_labels(self):
        formatter = PrometheusFormatter()
        metrics = [
            Metric(
                name="plone_content_total",
                value=42,
                type="gauge",
                scope="global",
                help="Content count",
                labels={"portal_type": "Document"},
            ),
        ]
        result = formatter.format(metrics)
        assert 'plone_content_total{scope="global",portal_type="Document"} 42' in result

    def test_format_info(self):
        formatter = PrometheusFormatter()
        metrics = [
            Metric(
                name="plone_info",
                value=1,
                type="gauge",
                scope="instance",
                help="Version information",
                labels={"plone_version": "6.1.0", "zope_version": "5.11"},
            ),
        ]
        result = formatter.format(metrics)
        assert "# TYPE plone_info gauge" in result
        assert 'plone_version="6.1.0"' in result

    def test_content_type(self):
        formatter = PrometheusFormatter()
        assert formatter.content_type == "text/plain; version=0.0.4; charset=utf-8"

    def test_format_multiple_metrics(self):
        formatter = PrometheusFormatter()
        metrics = [
            Metric("plone_a", 1, "gauge", "instance", "A"),
            Metric("plone_b", 2, "gauge", "global", "B"),
        ]
        result = formatter.format(metrics)
        assert "plone_a" in result
        assert "plone_b" in result

    def test_format_integer_value(self):
        formatter = PrometheusFormatter()
        metrics = [
            Metric("plone_count", 42, "gauge", "instance", "Count"),
        ]
        result = formatter.format(metrics)
        assert 'plone_count{scope="instance"} 42' in result


class TestJSONFormatter:
    def test_format_basic(self):
        import json

        formatter = JSONFormatter()
        metrics = [
            Metric(
                name="plone_uptime_seconds",
                value=1234.5,
                type="gauge",
                scope="instance",
                help="Uptime",
            ),
        ]
        result = json.loads(formatter.format(metrics))
        assert len(result) == 1
        assert result[0]["name"] == "plone_uptime_seconds"
        assert result[0]["value"] == 1234.5
        assert result[0]["type"] == "gauge"
        assert result[0]["scope"] == "instance"

    def test_format_with_labels(self):
        import json

        formatter = JSONFormatter()
        metrics = [
            Metric(
                name="plone_content_total",
                value=42,
                type="gauge",
                scope="global",
                help="Count",
                labels={"portal_type": "Document"},
            ),
        ]
        result = json.loads(formatter.format(metrics))
        assert result[0]["labels"] == {"portal_type": "Document"}

    def test_content_type(self):
        formatter = JSONFormatter()
        assert formatter.content_type == "application/json"
