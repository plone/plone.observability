import pytest


@pytest.fixture
def catalog_module():
    from plone.observability.otel import catalog

    yield catalog
    catalog.uninstrument_catalog()


def test_wrapper_traces_all_query_entry_points(
    span_exporter, monkeypatch, catalog_module
):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")

    class FakeTool:
        def searchResults(self, query=None, **kw):
            return [1, 2, 3]

        __call__ = searchResults  # alias, like pgcatalog

        def unrestrictedSearchResults(self, **kw):
            return [1]

    catalog_module._instrument_class(FakeTool)
    tool = FakeTool()

    assert tool.searchResults() == [1, 2, 3]
    assert tool() == [1, 2, 3]  # __call__ alias must be re-pointed to the wrapper
    assert tool.unrestrictedSearchResults() == [1]

    names = [s.name for s in span_exporter.get_finished_spans()]
    assert names.count("catalog.searchResults") == 2  # direct call + __call__ alias
    assert "catalog.unrestrictedSearchResults" in names
    search = next(
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "catalog.searchResults"
    )
    assert search.attributes["plone.catalog.result_count"] == 3


def test_noop_when_disabled(span_exporter, monkeypatch, catalog_module):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")

    class FakeTool:
        def searchResults(self, query=None, **kw):
            return [1]

    catalog_module._instrument_class(FakeTool)
    FakeTool().searchResults()
    assert span_exporter.get_finished_spans() == ()


def test_instrument_catalog_wraps_standard_plone(catalog_module):
    from Products.CMFPlone.CatalogTool import CatalogTool

    catalog_module.instrument_catalog()
    assert getattr(CatalogTool.searchResults, "_otel_wrapped", False) is True
    assert (
        getattr(CatalogTool.unrestrictedSearchResults, "_otel_wrapped", False) is True
    )


def test_instrument_catalog_wraps_pgcatalog_when_installed(catalog_module):
    pytest.importorskip("plone.pgcatalog")
    from plone.pgcatalog.catalog import PlonePGCatalogTool

    catalog_module.instrument_catalog()
    assert getattr(PlonePGCatalogTool.searchResults, "_otel_wrapped", False) is True
    # __call__ is an alias of searchResults and must point at the wrapper too
    assert PlonePGCatalogTool.__call__ is PlonePGCatalogTool.searchResults
