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


def test_filter_activates_when_enabled(monkeypatch):
    from plone.observability.otel import catalog
    from plone.observability.otel import provider
    from plone.observability.otel import wsgi
    from plone.observability.otel import zodb

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    monkeypatch.setattr(zodb, "register", lambda: calls.append("zodb"))
    monkeypatch.setattr(catalog, "instrument_catalog", lambda: calls.append("catalog"))
    wsgi.make_filter(object(), {})
    assert calls == ["setup", "zodb", "catalog"]


def test_filter_skips_when_disabled(monkeypatch):
    from plone.observability.otel import provider
    from plone.observability.otel import wsgi

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    wsgi.make_filter(object(), {})
    assert calls == []
