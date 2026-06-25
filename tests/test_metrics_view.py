from plone.observability.interfaces import IMetricFormatter
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from plone.observability.metrics.view import MetricsView
from unittest import mock
from zope.component import getGlobalSiteManager
from zope.interface import implementer


@implementer(IMetricFormatter)
class StubFormatter:
    content_type = "text/plain"

    def format(self, metrics):
        return "\n".join(f"{m.name}={m.value}" for m in metrics)


@implementer(IMetricProvider)
class StubProvider:
    name = "stub"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        yield Metric("test_metric", 42, "gauge", "instance", "A test")


class FakeRequest:
    def __init__(self, accept="text/plain", format_param=None):
        self.environ = {"REMOTE_ADDR": "127.0.0.1"}
        self._accept = accept
        self._format_param = format_param
        self.response = FakeResponse()

    def get(self, key, default=None):
        if key == "format":
            return self._format_param
        return default

    def getHeader(self, name, default=None):
        if name.lower() == "accept":
            return self._accept
        if name.lower() == "x-forwarded-for":
            return None
        return default


class FakeResponse:
    def __init__(self):
        self.headers = {}
        self._status = 200

    def setHeader(self, name, value):
        self.headers[name] = value

    def setStatus(self, status):
        self._status = status


class FakeApp:
    pass


class TestMetricsView:
    def setup_method(self):
        self.gsm = getGlobalSiteManager()

    def teardown_method(self):
        # Clean up registrations
        self.gsm.unregisterUtility(provided=IMetricFormatter, name="prometheus")
        self.gsm.unregisterUtility(provided=IMetricFormatter, name="json")
        self.gsm.unregisterAdapter(
            factory=StubProvider,
            required=(None,),
            provided=IMetricProvider,
            name="stub",
        )

    def test_returns_formatted_metrics(self):
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "prometheus")
        self.gsm.registerAdapter(
            StubProvider, required=(None,), provided=IMetricProvider, name="stub"
        )
        request = FakeRequest()
        view = MetricsView(FakeApp(), request)
        result = view()
        assert "test_metric=42" in result

    def test_format_query_param_overrides_accept(self):
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "json")
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "prometheus")
        self.gsm.registerAdapter(
            StubProvider, required=(None,), provided=IMetricProvider, name="stub"
        )
        request = FakeRequest(format_param="json")
        view = MetricsView(FakeApp(), request)
        result = view()
        assert "test_metric=42" in result

    @mock.patch("plone.observability.metrics.view.is_allowed", return_value=False)
    def test_returns_403_when_not_allowed(self, mock_allowed):
        request = FakeRequest()
        view = MetricsView(FakeApp(), request)
        view()
        assert request.response._status == 403


@implementer(IMetricProvider)
class BoomProvider:
    def __init__(self, context):
        self.context = context

    def collect(self):
        raise RuntimeError("boom")


class TestMetricsViewCoverage:
    def setup_method(self):
        self.gsm = getGlobalSiteManager()

    def teardown_method(self):
        self.gsm.unregisterUtility(provided=IMetricFormatter, name="prometheus")
        self.gsm.unregisterUtility(provided=IMetricFormatter, name="json")
        self.gsm.unregisterAdapter(
            factory=StubProvider,
            required=(None,),
            provided=IMetricProvider,
            name="stub",
        )
        self.gsm.unregisterAdapter(
            factory=BoomProvider,
            required=(None,),
            provided=IMetricProvider,
            name="boom",
        )

    def test_no_formatter_returns_500(self):
        # No formatter registered at all
        request = FakeRequest()
        view = MetricsView(FakeApp(), request)
        result = view()
        assert request.response._status == 500
        assert "No metric formatter" in result

    def test_provider_error_is_logged_and_skipped(self):
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "prometheus")
        self.gsm.registerAdapter(
            BoomProvider, required=(None,), provided=IMetricProvider, name="boom"
        )
        request = FakeRequest()
        view = MetricsView(FakeApp(), request)
        result = view()  # must not raise
        assert result == ""  # no metrics collected, formatter yields empty

    def test_accept_header_selects_json(self):
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "json")
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "prometheus")
        self.gsm.registerAdapter(
            StubProvider, required=(None,), provided=IMetricProvider, name="stub"
        )
        request = FakeRequest(accept="application/json", format_param=None)
        view = MetricsView(FakeApp(), request)
        assert "test_metric=42" in view()

    def test_unknown_format_param_falls_back(self):
        self.gsm.registerUtility(StubFormatter(), IMetricFormatter, "prometheus")
        self.gsm.registerAdapter(
            StubProvider, required=(None,), provided=IMetricProvider, name="stub"
        )
        request = FakeRequest(format_param="nope")  # not registered -> fall through
        view = MetricsView(FakeApp(), request)
        assert "test_metric=42" in view()
