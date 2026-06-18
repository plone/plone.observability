import pytest


@pytest.fixture(scope="module")
def zcml_loaded():
    """Load the package ZCML, which conditionally includes the otel config."""
    import Products.Five
    import zope.component
    from zope.configuration import xmlconfig
    from zope.configuration.config import ConfigurationMachine

    context = ConfigurationMachine()
    xmlconfig.registerCommonDirectives(context)
    xmlconfig.include(context, "meta.zcml", zope.component)
    xmlconfig.include(context, "meta.zcml", Products.Five)

    import plone.observability

    xmlconfig.include(context, "configure.zcml", plone.observability)
    context.execute_actions()
    yield context


def test_otel_zcml_registers_pubevent_subscribers(zcml_loaded):
    """The conditional otel include must wire the publish-start subscriber."""
    from zope.component import getGlobalSiteManager
    from ZPublisher.interfaces import IPubStart
    from plone.observability.otel import pubevents

    gsm = getGlobalSiteManager()
    handlers = [
        h.handler
        for h in gsm.registeredHandlers()
        if IPubStart in getattr(h, "required", ())
    ]
    assert pubevents.on_pub_start in handlers


def test_startup_activates_when_enabled(monkeypatch):
    from plone.observability.otel import startup
    from plone.observability.otel import provider

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    monkeypatch.setattr(
        "plone.observability.otel.zodb.register", lambda: calls.append("zodb")
    )
    monkeypatch.setattr(
        "plone.observability.otel.catalog.instrument_catalog",
        lambda: calls.append("catalog"),
    )
    startup.on_process_starting(object())
    assert calls == ["setup", "zodb", "catalog"]


def test_startup_skips_when_disabled(monkeypatch):
    from plone.observability.otel import startup
    from plone.observability.otel import provider

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    startup.on_process_starting(object())
    assert calls == []
