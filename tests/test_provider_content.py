from unittest import mock

from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.content import ContentMetricProvider
from zope.interface.verify import verifyObject


class FakeIndex:
    def __init__(self, values):
        self._values = values

    def uniqueValues(self, withLengths=False):
        if withLengths:
            return self._values
        return [v[0] for v in self._values]


class FakeCatalog:
    def __init__(self, portal_type_values, review_state_values):
        self.Indexes = {
            "portal_type": FakeIndex(portal_type_values),
            "review_state": FakeIndex(review_state_values),
        }


class FakeSite:
    id = "Plone"

    def __init__(self, catalog):
        self._catalog = catalog

    def unrestrictedTraverse(self, path, default=None):
        if path == "portal_catalog":
            return self._catalog
        return default


class FakeApp:
    _p_jar = None

    def __init__(self, sites=None):
        self._sites = sites or []

    def objectValues(self):
        return self._sites


class TestContentMetricProvider:
    def _make_provider(self):
        catalog = FakeCatalog(
            portal_type_values=[("Document", 100), ("Folder", 50)],
            review_state_values=[("published", 80), ("private", 70)],
        )
        site = FakeSite(catalog)
        app = FakeApp(sites=[site])
        # Mock _find_plone_sites to return our fake site
        with mock.patch(
            "plone.observability.metrics.providers.content._find_plone_sites",
            return_value=[site],
        ):
            provider = ContentMetricProvider(app)
            return provider

    def test_implements_interface(self):
        provider = self._make_provider()
        assert verifyObject(IMetricProvider, provider)

    def test_scope_is_global(self):
        provider = self._make_provider()
        assert provider.scope == "global"

    def test_collects_content_by_type(self):
        provider = self._make_provider()
        with mock.patch(
            "plone.observability.metrics.providers.content._find_plone_sites",
            return_value=[
                FakeSite(
                    FakeCatalog(
                        [("Document", 100), ("Folder", 50)],
                        [("published", 80), ("private", 70)],
                    )
                )
            ],
        ):
            metrics = list(provider.collect())
        type_metrics = [m for m in metrics if m.name == "plone_content_total"]
        assert len(type_metrics) == 2
        docs = [m for m in type_metrics if m.labels.get("portal_type") == "Document"]
        assert len(docs) == 1
        assert docs[0].value == 100

    def test_collects_content_by_state(self):
        provider = self._make_provider()
        with mock.patch(
            "plone.observability.metrics.providers.content._find_plone_sites",
            return_value=[
                FakeSite(
                    FakeCatalog(
                        [("Document", 100)],
                        [("published", 80), ("private", 70)],
                    )
                )
            ],
        ):
            metrics = list(provider.collect())
        state_metrics = [m for m in metrics if m.name == "plone_content_by_state"]
        assert len(state_metrics) == 2
        published = [m for m in state_metrics if m.labels.get("state") == "published"]
        assert len(published) == 1
        assert published[0].value == 80

    def test_no_sites_returns_empty(self):
        app = FakeApp(sites=[])
        provider = ContentMetricProvider(app)
        with mock.patch(
            "plone.observability.metrics.providers.content._find_plone_sites",
            return_value=[],
        ):
            metrics = list(provider.collect())
        assert metrics == []


class TestContentProviderStepsAside:
    def test_non_zcatalog_yields_nothing_without_raising(self):
        from unittest import mock

        from plone.observability.metrics.providers.content import (
            ContentMetricProvider,
        )

        class WeirdCatalog:
            @property
            def Indexes(self):
                raise RuntimeError("no such API on this backend")

        class Site:
            id = "Plone"

            def unrestrictedTraverse(self, path, default=None):
                return WeirdCatalog() if path == "portal_catalog" else default

        site = Site()
        with mock.patch(
            "plone.observability.metrics.providers.content._find_plone_sites",
            return_value=[site],
        ):
            provider = ContentMetricProvider(object())
            metrics = list(provider.collect())
        assert metrics == []
