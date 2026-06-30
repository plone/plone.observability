from plone.app.testing import FunctionalTesting
from plone.app.testing import IntegrationTesting
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import PloneSandboxLayer

import plone.observability
import pytest


class PloneObservabilityLayer(PloneSandboxLayer):
    defaultBases = (PLONE_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        self.loadZCML(package=plone.observability)


PLONE_OBSERVABILITY_FIXTURE = PloneObservabilityLayer()

PLONE_OBSERVABILITY_INTEGRATION_TESTING = IntegrationTesting(
    bases=(PLONE_OBSERVABILITY_FIXTURE,),
    name="PloneObservabilityLayer:IntegrationTesting",
)

PLONE_OBSERVABILITY_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(PLONE_OBSERVABILITY_FIXTURE,),
    name="PloneObservabilityLayer:FunctionalTesting",
)


@pytest.fixture(scope="session")
def _otel_provider():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)  # set once per test session
    return exporter


@pytest.fixture
def span_exporter(_otel_provider):
    _otel_provider.clear()
    yield _otel_provider
    _otel_provider.clear()


@pytest.fixture(autouse=True)
def _reset_otel_exclusions_cache():
    """Excluded-URL config is memoized at module level; reset it per test so
    one test's env does not leak into the next."""
    try:
        from plone.observability.otel import exclusions
    except ImportError:
        yield
        return
    exclusions.reset_cache()
    yield
    exclusions.reset_cache()
