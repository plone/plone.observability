from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.zope_runtime import (
    ZopeRuntimeMetricProvider,
)
from zope.interface.verify import verifyObject


class FakeApp:
    pass


class TestZopeRuntimeMetricProvider:
    def test_implements_interface(self):
        provider = ZopeRuntimeMetricProvider(FakeApp())
        assert verifyObject(IMetricProvider, provider)

    def test_scope_is_instance(self):
        provider = ZopeRuntimeMetricProvider(FakeApp())
        assert provider.scope == "instance"

    def test_collects_uptime(self):
        provider = ZopeRuntimeMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_uptime_seconds" in metrics
        assert metrics["plone_uptime_seconds"].value >= 0

    def test_collects_info(self):
        provider = ZopeRuntimeMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_info" in metrics
        info = metrics["plone_info"]
        assert info.type == "gauge"
        assert "python_version" in info.labels
        assert "zope_version" in info.labels

    def test_collects_thread_metrics(self):
        provider = ZopeRuntimeMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_threads_active" in metrics
        assert metrics["plone_threads_active"].value > 0
