from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.zodb import ZODBMetricProvider
from zope.interface.verify import verifyObject


class FakePool:
    size = 7


class FakeStorage:
    pass


class FakeDB:
    database_name = "main"
    pool = FakePool()
    storage = FakeStorage()
    _activity_monitor = None

    def getActivityMonitor(self):
        return self._activity_monitor

    def setActivityMonitor(self, monitor):
        self._activity_monitor = monitor

    def objectCount(self):
        return 5000

    def getSize(self):
        return 1048576

    def cacheSize(self):
        return 200

    def getCacheSizeBytes(self):
        return 524288


class FakeJar:
    def __init__(self):
        self._db = FakeDB()

    def db(self):
        return self._db


class FakeApp:
    def __init__(self):
        self._p_jar = FakeJar()


class TestZODBMetricProvider:
    def test_implements_interface(self):
        provider = ZODBMetricProvider(FakeApp())
        assert verifyObject(IMetricProvider, provider)

    def test_scope_is_global(self):
        provider = ZODBMetricProvider(FakeApp())
        assert provider.scope == "global"

    def test_collects_object_count(self):
        provider = ZODBMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_zodb_object_count" in metrics
        assert metrics["plone_zodb_object_count"].value == 5000
        assert metrics["plone_zodb_object_count"].scope == "global"

    def test_collects_db_size(self):
        provider = ZODBMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_zodb_db_size_bytes" in metrics
        assert metrics["plone_zodb_db_size_bytes"].value == 1048576

    def test_collects_connection_count(self):
        provider = ZODBMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_zodb_connections" in metrics
        assert metrics["plone_zodb_connections"].value == 7
        assert metrics["plone_zodb_connections"].scope == "instance"

    def test_collects_cache_metrics(self):
        provider = ZODBMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_zodb_cache_size" in metrics
        assert metrics["plone_zodb_cache_size"].scope == "instance"

    def test_all_metrics_have_database_label(self):
        provider = ZODBMetricProvider(FakeApp())
        for m in provider.collect():
            assert "database" in m.labels
            assert m.labels["database"] == "main"

    def test_no_crash_without_p_jar(self):
        class NoJarApp:
            pass

        provider = ZODBMetricProvider(NoJarApp())
        metrics = list(provider.collect())
        assert metrics == []


class TestLoadStoreActivityMonitor:
    def test_accumulates_transfer_counts(self):
        from plone.observability.metrics.providers.zodb import LoadStoreActivityMonitor

        class FakeConn:
            def __init__(self, counts):
                self._counts = list(counts)

            def getTransferCounts(self, clear=False):
                return self._counts.pop(0)

        mon = LoadStoreActivityMonitor()
        conn = FakeConn([(3, 1), (2, 0)])
        mon.closedConnection(conn)
        mon.closedConnection(conn)
        assert mon.loads == 5
        assert mon.stores == 1


class FakeMonitorDB:
    def __init__(self, existing=None):
        self._monitor = existing

    def getActivityMonitor(self):
        return self._monitor

    def setActivityMonitor(self, monitor):
        self._monitor = monitor


class TestEnsureActivityMonitor:
    def _reset(self, monkeypatch):
        from plone.observability.metrics.providers import zodb

        monkeypatch.setattr(zodb, "_monitor", None)
        monkeypatch.setattr(zodb, "_warned_foreign", False)
        return zodb

    def test_installs_when_slot_empty_and_enabled(self, monkeypatch):
        zodb = self._reset(monkeypatch)
        monkeypatch.delenv("PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR", raising=False)
        db = FakeMonitorDB(existing=None)
        zodb._ensure_activity_monitor(db)
        assert isinstance(db.getActivityMonitor(), zodb.LoadStoreActivityMonitor)
        assert zodb._monitor is db.getActivityMonitor()

    def test_disabled_via_env(self, monkeypatch):
        zodb = self._reset(monkeypatch)
        monkeypatch.setenv("PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR", "0")
        db = FakeMonitorDB(existing=None)
        zodb._ensure_activity_monitor(db)
        assert db.getActivityMonitor() is None
        assert zodb._monitor is None

    def test_does_not_override_foreign_monitor(self, monkeypatch):
        zodb = self._reset(monkeypatch)
        monkeypatch.delenv("PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR", raising=False)
        foreign = object()
        db = FakeMonitorDB(existing=foreign)
        zodb._ensure_activity_monitor(db)
        assert db.getActivityMonitor() is foreign
        assert zodb._monitor is None


class TestZODBLoadStoreMetrics:
    def test_emits_loads_stores_counters(self, monkeypatch):
        from plone.observability.metrics.providers import zodb

        monkeypatch.setattr(zodb, "_monitor", None)
        monkeypatch.setattr(zodb, "_warned_foreign", False)
        monkeypatch.delenv("PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR", raising=False)

        provider = zodb.ZODBMetricProvider(FakeApp())
        list(provider.collect())  # triggers lazy install on FakeDB

        zodb._monitor.loads = 42
        zodb._monitor.stores = 7

        metrics = {m.name: m for m in provider.collect()}
        assert metrics["plone_zodb_loads_total"].value == 42
        assert metrics["plone_zodb_loads_total"].type == "counter"
        assert metrics["plone_zodb_loads_total"].scope == "instance"
        assert metrics["plone_zodb_stores_total"].value == 7
        assert "database" in metrics["plone_zodb_loads_total"].labels

    def test_no_loads_counters_when_foreign_monitor(self, monkeypatch):
        from plone.observability.metrics.providers import zodb

        monkeypatch.setattr(zodb, "_monitor", None)
        monkeypatch.setattr(zodb, "_warned_foreign", False)

        app = FakeApp()
        app._p_jar.db()._activity_monitor = object()  # foreign monitor present

        provider = zodb.ZODBMetricProvider(app)
        metrics = {m.name: m for m in provider.collect()}
        assert "plone_zodb_loads_total" not in metrics
        assert "plone_zodb_stores_total" not in metrics
