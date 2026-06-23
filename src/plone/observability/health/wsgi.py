"""Serving-only startup of the health server via a PasteDeploy filter.

The WSGI pipeline (zope.ini) is only built when the server actually serves;
zconsole/scripts load zope.conf via make_wsgi_app and never build the pipeline.
So this filter is a serving-only hook and never runs under zconsole.
"""

import logging

import Zope2
from zope.component import queryUtility

from plone.observability.health.server import HealthServer
from plone.observability.interfaces import IReadinessCheck


logger = logging.getLogger(__name__)

_health_server = HealthServer()


def make_filter(app, global_conf, **local_conf):
    """PasteDeploy filter factory: start the health server (serving only)."""
    db = Zope2.DB
    _health_server.db = db
    zodb_check = queryUtility(IReadinessCheck, name="zodb")
    if zodb_check is not None:
        zodb_check.db = db
    logger.info("Starting plone.observability health server")
    _health_server.start()
    return app
