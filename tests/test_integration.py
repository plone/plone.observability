"""Integration tests verifying ZCA registrations work together."""

import json

import pytest

from zope.component import getUtilitiesFor
from zope.component import queryUtility
from zope.configuration import xmlconfig

from plone.observability.interfaces import IMetricFormatter
from plone.observability.interfaces import IReadinessCheck
from plone.observability.metric import Metric


@pytest.fixture(scope="module")
def zcml_loaded():
    """Load the package ZCML to register all components.

    Bootstraps the ZCML machinery with the meta directives required for the
    ``zope`` and ``browser`` namespaces before loading plone.observability's
    own configuration.
    """
    import Products.Five
    import zope.component
    from zope.configuration.config import ConfigurationMachine

    context = ConfigurationMachine()
    xmlconfig.registerCommonDirectives(context)
    xmlconfig.include(context, "meta.zcml", zope.component)
    xmlconfig.include(context, "meta.zcml", Products.Five)

    import plone.observability

    xmlconfig.include(context, "configure.zcml", plone.observability)
    context.execute_actions()
    yield context


class TestZCARegistrations:
    def test_formatters_registered(self, zcml_loaded):
        prometheus = queryUtility(IMetricFormatter, name="prometheus")
        assert prometheus is not None
        json_fmt = queryUtility(IMetricFormatter, name="json")
        assert json_fmt is not None

    def test_readiness_check_registered(self, zcml_loaded):
        checks = dict(getUtilitiesFor(IReadinessCheck))
        assert "zodb" in checks

    def test_prometheus_formatter_produces_output(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="prometheus")
        metrics = [
            Metric("plone_test", 42, "gauge", "instance", "Test metric"),
        ]
        output = formatter.format(metrics)
        assert "# HELP plone_test" in output
        assert "# TYPE plone_test gauge" in output
        assert "42" in output

    def test_json_formatter_produces_valid_json(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="json")
        metrics = [
            Metric("plone_test", 42, "gauge", "instance", "Test metric"),
        ]
        output = formatter.format(metrics)
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["name"] == "plone_test"

    def test_prometheus_formatter_content_type(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="prometheus")
        assert "text/plain" in formatter.content_type

    def test_json_formatter_content_type(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="json")
        assert formatter.content_type == "application/json"

    def test_prometheus_formatter_multiple_metrics(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="prometheus")
        metrics = [
            Metric("plone_foo", 1, "counter", "instance", "Foo counter"),
            Metric("plone_bar", 99.5, "gauge", "global", "Bar gauge"),
        ]
        output = formatter.format(metrics)
        assert "# HELP plone_foo" in output
        assert "# TYPE plone_foo counter" in output
        assert "# HELP plone_bar" in output
        assert "# TYPE plone_bar gauge" in output
        assert "99.5" in output

    def test_prometheus_formatter_labels(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="prometheus")
        metrics = [
            Metric(
                "plone_content_total",
                10,
                "gauge",
                "global",
                "Content by type",
                labels={"portal_type": "Document"},
            ),
        ]
        output = formatter.format(metrics)
        assert 'portal_type="Document"' in output

    def test_json_formatter_with_labels(self, zcml_loaded):
        formatter = queryUtility(IMetricFormatter, name="json")
        metrics = [
            Metric(
                "plone_content_total",
                5,
                "gauge",
                "global",
                "Content by type",
                labels={"portal_type": "News Item"},
            ),
        ]
        output = formatter.format(metrics)
        data = json.loads(output)
        assert data[0]["labels"] == {"portal_type": "News Item"}

    def test_zodb_readiness_check_no_db(self, zcml_loaded):
        """ZODBReadinessCheck returns failure gracefully when no DB is set."""
        checks = dict(getUtilitiesFor(IReadinessCheck))
        zodb_check = checks["zodb"]
        # The check is registered but has no DB wired yet
        ok, message = zodb_check()
        assert ok is False
        assert "No database" in message


class TestConflictRegistration:
    def test_conflict_provider_registered(self, zcml_loaded):
        from OFS.interfaces import IApplication
        from zope.component import getGlobalSiteManager

        from plone.observability.interfaces import IMetricProvider
        from plone.observability.metrics.providers.conflict import (
            ConflictMetricProvider,
        )

        gsm = getGlobalSiteManager()
        adapter = gsm.adapters.lookup((IApplication,), IMetricProvider, name="conflict")
        assert adapter is ConflictMetricProvider

    def test_conflict_subscriber_registered(self, zcml_loaded):
        from zope.component import getGlobalSiteManager
        from ZPublisher.interfaces import IPubBeforeAbort

        from plone.observability.metrics.providers import conflict

        gsm = getGlobalSiteManager()
        handlers = [
            h.handler
            for h in gsm.registeredHandlers()
            if IPubBeforeAbort in getattr(h, "required", ())
        ]
        assert conflict.on_pub_before_abort in handlers
