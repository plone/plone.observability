"""Catalog query span instrumentation, backend-agnostic.

Catalog tools emit no events, so this wraps the tool-level query methods
(searchResults / unrestrictedSearchResults / the __call__ alias) -- the one
sanctioned, reversible monkeypatch. It targets every importable catalog tool
class so it works for both standard Plone (Products.CMFPlone CatalogTool) and
plone-pgcatalog (plone.pgcatalog PlonePGCatalogTool), which is a standalone tool
that never touches ZCatalog's low-level search.
"""

from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.spans import start_span


_QUERY_METHODS = ("searchResults", "unrestrictedSearchResults")

# list of (cls, name, original) we replaced, for uninstrument
_patched = []


def _make_wrapper(span_name, original):
    def wrapper(self, *args, **kwargs):
        if not is_enabled() or exclusions.is_suppressed():
            return original(self, *args, **kwargs)
        with start_span(span_name) as span:
            results = original(self, *args, **kwargs)
            if span is not None:
                try:
                    span.set_attribute("plone.catalog.result_count", len(results))
                except TypeError:
                    pass
            return results

    wrapper._otel_wrapped = True
    wrapper._otel_original = original
    return wrapper


def _instrument_class(cls):
    wrapped_search = None
    original_search = None
    for name in _QUERY_METHODS:
        # Prefer the method defined on the class; fall back to an inherited one
        # (e.g. CatalogTool inherits unrestrictedSearchResults).
        original = cls.__dict__.get(name) or getattr(cls, name, None)
        if original is None or getattr(original, "_otel_wrapped", False):
            continue
        wrapper = _make_wrapper(f"catalog.{name}", original)
        setattr(cls, name, wrapper)
        _patched.append((cls, name, original))
        if name == "searchResults":
            original_search = original
            wrapped_search = wrapper

    # Re-point __call__ only when it is the *same object* as the original
    # searchResults (pgcatalog's `__call__ = searchResults` alias). Standard
    # Plone's __call__ delegates to self.searchResults and is already covered.
    if wrapped_search is not None and cls.__dict__.get("__call__") is original_search:
        cls.__call__ = wrapped_search
        _patched.append((cls, "__call__", original_search))


def _tool_classes():
    classes = []
    try:
        from Products.CMFPlone.CatalogTool import CatalogTool

        classes.append(CatalogTool)
    except ImportError:
        pass
    try:
        from plone.pgcatalog.catalog import PlonePGCatalogTool

        classes.append(PlonePGCatalogTool)
    except ImportError:
        pass
    return classes


def instrument_catalog():
    if _patched:
        return
    for cls in _tool_classes():
        _instrument_class(cls)


def uninstrument_catalog():
    while _patched:
        cls, name, original = _patched.pop()
        setattr(cls, name, original)
