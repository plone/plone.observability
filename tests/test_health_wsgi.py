import importlib

import pytest


def test_make_filter_wires_db_starts_and_passes_through(monkeypatch):
    import Zope2
    from zope.component import getGlobalSiteManager
    from zope.interface import implementer

    from plone.observability.health import wsgi
    from plone.observability.interfaces import IReadinessCheck

    fake_db = object()
    monkeypatch.setattr(Zope2, "DB", fake_db, raising=False)

    started = []
    monkeypatch.setattr(wsgi._health_server, "start", lambda: started.append(True))

    @implementer(IReadinessCheck)
    class StubCheck:
        name = "zodb"
        db = None

        def __call__(self):
            return True, "ok"

    gsm = getGlobalSiteManager()
    stub = StubCheck()
    gsm.registerUtility(stub, IReadinessCheck, name="zodb")
    try:
        sentinel = object()
        result = wsgi.make_filter(sentinel, {})
        assert result is sentinel
        assert wsgi._health_server.db is fake_db
        assert stub.db is fake_db
        assert started == [True]
    finally:
        gsm.unregisterUtility(stub, IReadinessCheck, name="zodb")


def test_old_startup_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("plone.observability.startup")
