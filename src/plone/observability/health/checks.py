from plone.observability.interfaces import IReadinessCheck
from zope.interface import implementer

import logging


logger = logging.getLogger(__name__)


@implementer(IReadinessCheck)
class ZODBReadinessCheck:
    """Verifies that the ZODB is accessible by opening a connection and reading the root."""

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
