from plone.base.utils import boolean_value
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import logging
import os
import threading
import time


logger = logging.getLogger(__name__)


# The two DB-wide gauges (object count, database size) are cheap on
# FileStorage but cost a full ``SELECT count(*)`` / relation-size query on
# Postgres-backed storage (zodb-pgjsonb) or RelStorage — seconds on a large
# DB, run on *every* scrape. They change slowly, so cache them with a TTL
# (shared env var with the content provider) keyed by database name. The
# cheap in-memory gauges and the load/store counters stay live per scrape.
_global_gauge_cache = {}  # database_name -> (timestamp, (object_count, db_size))
_global_gauge_lock = threading.Lock()


def _cache_ttl():
    return int(os.environ.get("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "60"))


def _expensive_global_gauges(db, db_name):
    """Return ``(object_count, db_size)`` for *db*, cached per database.

    The expensive queries run at most once per TTL window. We compute outside
    the lock so a slow query never serializes concurrent scrapes behind it.
    """
    now = time.time()
    with _global_gauge_lock:
        entry = _global_gauge_cache.get(db_name)
        if entry is not None and (now - entry[0]) < _cache_ttl():
            return entry[1]

    object_count = db.objectCount()
    db_size = db.getSize()
    if isinstance(db_size, str):
        try:
            db_size = float(db_size)
        except (ValueError, TypeError):
            db_size = 0

    value = (object_count, db_size)
    with _global_gauge_lock:
        _global_gauge_cache[db_name] = (now, value)
    return value


class LoadStoreActivityMonitor:
    """Minimal ZODB activity monitor: cumulative load/store totals.

    Installed in the DB's single activity-monitor slot. ZODB calls
    closedConnection() on every connection close (~once per request); we read
    and reset the connection's transfer counts and add them to process-wide
    totals. O(1) memory, no history log.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.loads = 0
        self.stores = 0

    def closedConnection(self, conn):
        loads, stores = conn.getTransferCounts(True)  # read and reset
        with self._lock:
            self.loads += loads
            self.stores += stores

    def getActivityAnalysis(self, start=0, end=0, divisions=10):
        # Part of ZODB's activity-monitor API surface; unused here.
        return []


_monitor = None  # our LoadStoreActivityMonitor, once installed
_monitor_lock = threading.Lock()
_warned_foreign = False


def _monitor_enabled():
    return boolean_value(
        os.environ.get("PLONE_OBSERVABILITY_ZODB_ACTIVITY_MONITOR", ""),
        default=True,
    )


def _ensure_activity_monitor(db):
    """Install our load/store monitor once, if the slot is free and enabled."""
    global _monitor, _warned_foreign
    if _monitor is not None or not _monitor_enabled():
        return
    with _monitor_lock:
        if _monitor is not None:
            return
        existing = db.getActivityMonitor()
        if existing is not None:
            if not _warned_foreign:
                logger.warning(
                    "ZODB activity monitor already set (%r); not installing "
                    "plone.observability load/store monitor, so "
                    "plone_zodb_loads_total/stores_total are unavailable",
                    existing,
                )
                _warned_foreign = True
            return
        monitor = LoadStoreActivityMonitor()
        db.setActivityMonitor(monitor)
        _monitor = monitor


@implementer(IMetricProvider)
class ZODBMetricProvider:
    """Provides ZODB database metrics."""

    name = "zodb"
    scope = "global"  # Mixed: some metrics are global, some instance

    def __init__(self, context):
        self.context = context

    def collect(self):
        try:
            db = self.context._p_jar.db()
        except AttributeError:
            logger.debug("No ZODB connection available on context")
            return

        db_name = getattr(db, "database_name", "main")
        labels = {"database": db_name}

        # Global metrics — these two are DB-wide queries that are expensive on
        # Postgres-backed storage, so they are TTL-cached (see module docstring).
        object_count, db_size = _expensive_global_gauges(db, db_name)
        yield Metric(
            name="plone_zodb_object_count",
            value=object_count,
            type="gauge",
            scope="global",
            help="Total number of objects in the ZODB",
            labels=labels,
        )

        yield Metric(
            name="plone_zodb_db_size_bytes",
            value=db_size,
            type="gauge",
            scope="global",
            help="Size of the ZODB database in bytes",
            labels=labels,
        )

        # Instance-specific metrics
        yield Metric(
            name="plone_zodb_connections",
            value=db.pool.size,
            type="gauge",
            scope="instance",
            help="Number of open ZODB connections in the pool",
            labels=labels,
        )

        yield Metric(
            name="plone_zodb_cache_size",
            value=db.cacheSize(),
            type="gauge",
            scope="instance",
            help="Number of objects in the ZODB cache",
            labels=labels,
        )

        yield Metric(
            name="plone_zodb_cache_size_bytes",
            value=db.getCacheSizeBytes(),
            type="gauge",
            scope="instance",
            help="Size of the ZODB cache in bytes",
            labels=labels,
        )

        # Load/store activity (storage-agnostic, via our activity monitor)
        _ensure_activity_monitor(db)
        if _monitor is not None:
            yield Metric(
                name="plone_zodb_loads_total",
                value=_monitor.loads,
                type="counter",
                scope="instance",
                help="Cumulative objects loaded from storage since monitor install",
                labels=labels,
            )
            yield Metric(
                name="plone_zodb_stores_total",
                value=_monitor.stores,
                type="counter",
                scope="instance",
                help="Cumulative objects stored to storage since monitor install",
                labels=labels,
            )
