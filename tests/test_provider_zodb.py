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
    _p_jar = FakeJar()


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
