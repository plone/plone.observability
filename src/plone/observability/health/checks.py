from plone.observability.interfaces import IReadinessCheck
from zope.interface import implementer

import logging


logger = logging.getLogger(__name__)


@implementer(IReadinessCheck)
class ZODBReadinessCheck:
    """Verifies that the ZODB is accessible by opening a connection and reading the root.

    The check deliberately goes through ``db.open()``, the path every request
    takes, including ``DB._lock``. A check against the storage alone would
    report ready while requests hang on that lock (zodb-pgjsonb#126).

    When all worker connections are busy, ``db.open()`` creates one beyond
    ``pool-size`` and ZODB logs "DB.open() has N open connections". That is
    harmless: the pool discards the connection with the smallest cache, which
    is the probe's, so warm worker caches survive (#92).
    """

    name = "zodb"

    def __init__(self):
        self.db = None  # Set during startup

    def __call__(self):
        if self.db is None:
            return False, "No database reference available"
        try:
            conn = self.db.open()
            try:
                conn.root()
                return True, "ZODB connection ok"
            finally:
                conn.close()
        except Exception as e:
            logger.warning("ZODB readiness check failed: %s", e)
            return False, f"ZODB connection failed: {e}"
