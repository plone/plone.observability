from persistent.mapping import PersistentMapping
from plone.observability.health.checks import ZODBReadinessCheck
from plone.observability.interfaces import IReadinessCheck
from zope.interface.verify import verifyObject

import transaction
import ZODB


class FakeConnection:
    def __init__(self, root_data=None, raise_on_root=False):
        self._root_data = root_data or {}
        self._raise_on_root = raise_on_root
        self.closed = False

    def root(self):
        if self._raise_on_root:
            raise Exception("ZODB connection failed")
        return self._root_data

    def close(self):
        self.closed = True


class FakeDB:
    def __init__(self, connection=None):
        self._connection = connection or FakeConnection({"Application": True})

    def open(self):
        return self._connection


class TestZODBReadinessCheck:
    def test_implements_interface(self):
        check = ZODBReadinessCheck()
        check.db = FakeDB()
        assert verifyObject(IReadinessCheck, check)

    def test_ok_when_db_is_readable(self):
        check = ZODBReadinessCheck()
        check.db = FakeDB()
        ok, message = check()
        assert ok is True
        assert "ok" in message.lower()

    def test_fail_when_no_db(self):
        check = ZODBReadinessCheck()
        check.db = None
        ok, message = check()
        assert ok is False

    def test_fail_when_db_raises(self):
        conn = FakeConnection(raise_on_root=True)
        check = ZODBReadinessCheck()
        check.db = FakeDB(connection=conn)
        ok, message = check()
        assert ok is False
        assert "failed" in message.lower() or "error" in message.lower()

    def test_connection_is_closed_after_check(self):
        conn = FakeConnection()
        check = ZODBReadinessCheck()
        check.db = FakeDB(connection=conn)
        check()
        assert conn.closed is True


class TestReadinessProbeOnSaturatedPool:
    """Pins the ZODB pool behaviour the check relies on (#92): the pool keeps
    idle connections sorted by cache size and discards the smallest, so a
    probe that overflows a saturated pool never evicts a warm worker cache."""

    def test_probe_does_not_evict_warm_caches(self):
        db = ZODB.DB(None, pool_size=3)
        try:
            conn = db.open()
            root = conn.root()
            for i in range(100):
                root[i] = PersistentMapping(v=i)
            transaction.commit()
            conn.close()

            # Three busy workers, each with a warm cache.
            workers = [
                db.open(transaction_manager=transaction.TransactionManager())
                for _ in range(3)
            ]
            for worker in workers:
                worker_root = worker.root()
                for i in range(100):
                    worker_root[i]["v"]
            warm = {id(worker) for worker in workers}

            class WorkerFinishesDuringProbe:
                # A worker returns its connection while the probe holds the
                # fourth one, so the probe's is not the oldest idle connection.
                def open(self):
                    conn = db.open()
                    workers[0].close()
                    return conn

            check = ZODBReadinessCheck()
            check.db = WorkerFinishesDuringProbe()
            ok, _ = check()
            assert ok is True

            for worker in workers[1:]:
                worker.close()
            assert {id(c) for c in db.pool.all} == warm
            assert all(c._cache.cache_non_ghost_count > 100 for c in db.pool.all)
        finally:
            db.close()
