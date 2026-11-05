from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.content import ContentMetricProvider
from unittest import mock
from zope.interface.verify import verifyObject

import pytest


@pytest.fixture(autouse=True)
def _clear_site_cache():
    """The content metrics are cached at module level per site id, and all
    fake sites here are called ``Plone``; clear the cache around each test."""
    from plone.observability.metrics.providers import content

    content._site_cache.clear()
    yield
    content._site_cache.clear()


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
        from plone.observability.metrics.providers.content import ContentMetricProvider
        from unittest import mock

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


class TestContentProviderCoverage:
    def test_find_plone_sites_filters_by_interface(self):
        from plone.observability.metrics.providers.content import _find_plone_sites
        from Products.CMFPlone.interfaces import IPloneSiteRoot
        from zope.interface import alsoProvides

        class Obj:
            pass

        site = Obj()
        alsoProvides(site, IPloneSiteRoot)
        other = Obj()

        class App:
            def objectValues(self):
                return [site, other]

        assert _find_plone_sites(App()) == [site]

    def test_collect_uses_cache_across_provider_instances(self, monkeypatch):
        # @@metrics builds a fresh adapter per scrape, so the cache must
        # outlive the provider instance.
        from plone.observability.metrics.providers import content

        catalog = FakeCatalog([("Document", 3)], [("published", 3)])
        index = catalog.Indexes["portal_type"]
        calls = {"n": 0}
        unique_values = index.uniqueValues

        def counting(withLengths=False):
            calls["n"] += 1
            return unique_values(withLengths=withLengths)

        index.uniqueValues = counting
        site = FakeSite(catalog)
        monkeypatch.setattr(content, "_find_plone_sites", lambda app: [site])
        first = list(content.ContentMetricProvider(object()).collect())
        second = list(content.ContentMetricProvider(object()).collect())
        assert calls["n"] == 1  # second scrape served from cache
        assert second == first

    def test_collect_refreshes_after_ttl(self, monkeypatch):
        from plone.observability.metrics.providers import content

        monkeypatch.setenv("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "0")
        values = [("Document", 3)]
        site = FakeSite(FakeCatalog(values, []))
        monkeypatch.setattr(content, "_find_plone_sites", lambda app: [site])
        list(content.ContentMetricProvider(object()).collect())
        values[0] = ("Document", 4)
        metrics = list(content.ContentMetricProvider(object()).collect())
        assert [m.value for m in metrics] == [4]

    def test_sites_are_cached_independently(self, monkeypatch):
        from plone.observability.metrics.providers import content

        one = FakeSite(FakeCatalog([("Document", 1)], []))
        one.id = "one"
        two = FakeSite(FakeCatalog([("Document", 2)], []))
        two.id = "two"
        sites = [one]
        monkeypatch.setattr(content, "_find_plone_sites", lambda app: list(sites))
        list(content.ContentMetricProvider(object()).collect())
        # A site added within the TTL window shows up on the next scrape.
        sites.append(two)
        metrics = list(content.ContentMetricProvider(object()).collect())
        assert {(m.labels["site"], m.value) for m in metrics} == {
            ("one", 1),
            ("two", 2),
        }

    def test_removed_site_is_evicted(self, monkeypatch):
        from plone.observability.metrics.providers import content

        one = FakeSite(FakeCatalog([("Document", 1)], []))
        one.id = "one"
        two = FakeSite(FakeCatalog([("Document", 2)], []))
        two.id = "two"
        sites = [one, two]
        monkeypatch.setattr(content, "_find_plone_sites", lambda app: list(sites))
        list(content.ContentMetricProvider(object()).collect())
        sites.remove(two)
        metrics = list(content.ContentMetricProvider(object()).collect())
        assert {m.labels["site"] for m in metrics} == {"one"}
        assert set(content._site_cache) == {"one"}

    def test_skips_site_without_catalog(self, monkeypatch):
        from plone.observability.metrics.providers import content

        class Site:
            id = "Plone"

            def unrestrictedTraverse(self, path, default=None):
                return default  # no portal_catalog

        monkeypatch.setattr(content, "_find_plone_sites", lambda app: [Site()])
        provider = content.ContentMetricProvider(object())
        assert list(provider.collect()) == []

    def test_emits_review_state_metrics(self, monkeypatch):
        from plone.observability.metrics.providers import content

        site = FakeSite(
            FakeCatalog(
                portal_type_values=[("Document", 3)],
                review_state_values=[("published", 2), ("private", 1)],
            )
        )
        monkeypatch.setattr(content, "_find_plone_sites", lambda app: [site])
        provider = content.ContentMetricProvider(object())
        names = [m.name for m in provider.collect()]
        assert "plone_content_by_state" in names
