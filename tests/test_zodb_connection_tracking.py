"""plone_zodb_connections_alive: every Connection still in memory (#94).

Run against real ``ZODB.DB`` instances: the point is to catch connections
the pool has released but something still references.
"""

from persistent.mapping import PersistentMapping
from plone.observability.metrics.providers import zodb

import gc
import transaction
import types
import ZODB


def alive(db):
    return len(db._plone_observability_alive)


def make_db(**kw):
    db = ZODB.DB(None, **kw)
    conn = db.open()
    root = conn.root()
    for i in range(50):
        root[i] = PersistentMapping(v=i)
    transaction.commit()
    conn.close()
    return db


def open_warm(db):
    conn = db.open(transaction_manager=transaction.TransactionManager())
    root = conn.root()
    for i in range(50):
        root[i]["v"]
    return conn


def full_gc():
    """A released connection takes two collections: the first frees its old
    object cache and objects, which reference the connection; the second
    frees the connection's own reference cycle."""
    gc.collect()
    gc.collect()


def release_all(db):
    """Make the pool release every idle connection, as an overflow does."""
    size = db.pool.size
    db.pool.size = 0
    db.pool.reduce_size()
    db.pool.size = size


class TestTracking:
    def test_seeds_connections_already_in_the_pool(self):
        db = make_db()
        zodb.track_connections(db)
        assert alive(db) == len(db.pool.all) == 1

    def test_tracks_new_connections(self):
        db = make_db()
        zodb.track_connections(db)
        conns = [open_warm(db) for _ in range(3)]
        assert alive(db) == 3
        for conn in conns:
            conn.close()

    def test_tracks_historical_connections(self):
        db = make_db()
        zodb.track_connections(db)
        conn = db.open(before=db.lastTransaction())
        assert conn in db._plone_observability_alive
        conn.close()

    def test_wraps_only_once(self):
        db = make_db()
        zodb.track_connections(db)
        klass = db.klass
        zodb.track_connections(db)
        assert db.klass is klass

    def test_wraps_a_configured_connection_class(self):
        # Zope sets DB.klass from zope.conf's connection-class.
        class MyConnection(ZODB.Connection.Connection):
            pass

        db = make_db()
        db.klass = MyConnection
        zodb.track_connections(db)
        pooled = db.open()  # the one ZODB.DB created for the root
        conn = db.open()  # a new one, from the wrapped class
        assert type(conn) is MyConnection
        assert conn in db._plone_observability_alive
        conn.close()
        pooled.close()

    def test_tracks_every_database_of_a_multi_database(self):
        databases = {}
        main = ZODB.DB(None, databases=databases, database_name="main")
        other = ZODB.DB(None, databases=databases, database_name="other")
        zodb.track_connections(main)
        conn = main.open()
        conn.get_connection("other")
        assert alive(main) == 1
        assert alive(other) == 1
        conn.close()

    def test_skips_databases_without_connection_class(self):
        fake = types.SimpleNamespace(database_name="main")
        zodb.track_connections(fake)
        assert not hasattr(fake, "_plone_observability_alive")


class TestReleasedConnections:
    def test_released_connection_disappears_when_unreferenced(self):
        db = make_db()
        zodb.track_connections(db)
        conn = open_warm(db)
        conn.close()
        del conn
        release_all(db)
        assert len(db.pool.all) == 0
        assert alive(db) == 1  # until the cyclic GC has run
        full_gc()
        assert alive(db) == 0

    def test_pinned_released_connection_stays_counted(self):
        db = make_db()
        zodb.track_connections(db)
        conn = open_warm(db)
        pinned = conn.root()[1]  # e.g. held by a stored traceback
        conn.close()
        del conn
        release_all(db)
        full_gc()
        assert len(db.pool.all) == 0
        assert alive(db) == 1
        del pinned
        full_gc()
        assert alive(db) == 0


class FakeEvent:
    def __init__(self, database):
        self.database = database


def test_startup_subscriber_tracks_the_database():
    db = make_db()
    zodb.track_connections_on_startup(FakeEvent(db))
    assert alive(db) == 1


class TestMetric:
    def test_provider_emits_alive_per_database(self):
        databases = {}
        main = make_db(databases=databases, database_name="main")
        ZODB.DB(None, databases=databases, database_name="other")
        conn = main.open()
        app = types.SimpleNamespace(_p_jar=conn)
        metrics = [
            m
            for m in zodb.ZODBMetricProvider(app).collect()
            if m.name == "plone_zodb_connections_alive"
        ]
        values = {m.labels["database"]: m.value for m in metrics}
        # "other" has the connection ZODB.DB opened to create its root.
        assert values == {"main": 1, "other": 1}
        assert all(m.type == "gauge" and m.scope == "instance" for m in metrics)
        conn.close()
