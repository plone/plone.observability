"""Excluded-URL handling shared by the WSGI filter and the span subscribers.

The bare ``OpenTelemetryMiddleware`` has no excluded-URL support, and the
publishing/catalog/zodb/transformchain spans are created from Zope events
*independently* of the WSGI middleware -- so excluding only the WSGI root span
would still leak the rest as root spans. This module is the single source of
truth for "is this path traced?", used by both layers:

- ``is_excluded(path)`` honours the standard
  ``OTEL_PYTHON_WSGI_EXCLUDED_URLS`` / ``OTEL_PYTHON_EXCLUDED_URLS`` env vars and,
  by default, the package's own ``@@metrics`` scrape endpoint. Defaults can be
  turned off with ``PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS=0``.
- ``suppress_token`` / ``is_suppressed`` mark a request excluded in the OTel
  context so the event-driven span subscribers skip span creation too.

Health probes (``/live`` etc.) are served by the separate HealthServer, never
through Zope/WSGI, so they produce no spans and need no exclusion here.
"""

from opentelemetry import context as otel_context
from opentelemetry.util.http import ExcludeList
from plone.base.utils import boolean_value

import os


# Always-noise endpoints owned by this package, excluded unless turned off.
DEFAULT_EXCLUDED_URLS = ("@@metrics",)

_SUPPRESS_KEY = otel_context.create_key("plone-observability-suppress-tracing")

_exclude_list = None


def _defaults_enabled():
    return boolean_value(
        os.environ.get("PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS", ""),
        default=True,
    )


def _build_exclude_list():
    patterns = list(DEFAULT_EXCLUDED_URLS) if _defaults_enabled() else []
    # WSGI-specific var wins; the generic one is the fallback (OTel convention).
    raw = os.environ.get("OTEL_PYTHON_WSGI_EXCLUDED_URLS")
    if raw is None:
        raw = os.environ.get("OTEL_PYTHON_EXCLUDED_URLS", "")
    patterns += [p.strip() for p in raw.split(",") if p.strip()]
    return ExcludeList(patterns)


def reset_cache():
    """Drop the memoized ExcludeList (env is read once, then cached)."""
    global _exclude_list
    _exclude_list = None


def is_excluded(path):
    global _exclude_list
    if _exclude_list is None:
        _exclude_list = _build_exclude_list()
    return _exclude_list.url_disabled(path or "")


# --- context suppression: make event-driven spans honour the same exclusion ---


def suppress_token():
    """Attach a context flagging tracing suppressed; return the detach token."""
    return otel_context.attach(otel_context.set_value(_SUPPRESS_KEY, True))


def detach(token):
    if token is not None:
        otel_context.detach(token)


def is_suppressed():
    return bool(otel_context.get_value(_SUPPRESS_KEY))
