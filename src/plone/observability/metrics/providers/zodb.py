import logging
import os
import threading

from zope.interface import implementer

from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric

logger = logging.getLogger(__name__)


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

        # Global metrics
        yield Metric(
            name="plone_zodb_object_count",
            value=db.objectCount(),
            type="gauge",
            scope="global",
            help="Total number of objects in the ZODB",
            labels=labels,
        )

        db_size = db.getSize()
        if isinstance(db_size, str):
            try:
                db_size = float(db_size)
            except (ValueError, TypeError):
                db_size = 0
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

        # Storage-level metrics (if available)
        storage = db.storage
        if hasattr(storage, "getTransactionCount"):
            yield Metric(
                name="plone_zodb_loads",
                value=getattr(storage, "_loads", 0),
                type="counter",
                scope="instance",
                help="Total number of object loads from storage",
                labels=labels,
            )
            yield Metric(
                name="plone_zodb_stores",
                value=getattr(storage, "_stores", 0),
                type="counter",
                scope="instance",
                help="Total number of object stores to storage",
                labels=labels,
            )
