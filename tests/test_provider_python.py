from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers import python
from plone.observability.metrics.providers.python import PythonMetricProvider
from zope.interface.verify import verifyObject

import gc
import pytest
import sys
import types


class FakeApp:
    pass


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """The GC pause tracker and the malloc cache are module-level; give every
    test a fresh tracker and an empty cache, and unhook the GC callback."""
    monkeypatch.setattr(python, "_gc_pauses", python.GCPauseTracker())
    monkeypatch.setattr(python, "_malloc_cache", None)
    monkeypatch.setattr(python, "_jemalloc_active", False)
    monkeypatch.setattr(python, "_warned_jemalloc", False)
    yield
    python._gc_pauses.uninstall()


def collect():
    return list(PythonMetricProvider(FakeApp()).collect())


def by_name(metrics, name):
    return [m for m in metrics if m.name == name]


class TestPythonMetricProvider:
    def test_implements_interface(self):
        assert verifyObject(IMetricProvider, PythonMetricProvider(FakeApp()))

    def test_all_metrics_are_instance_scope(self, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        assert all(m.scope == "instance" for m in collect())

    def test_allocated_blocks(self, monkeypatch):
        monkeypatch.setattr(python.sys, "getallocatedblocks", lambda: 4711)
        (metric,) = by_name(collect(), "plone_python_allocated_blocks")
        assert metric.value == 4711
        assert metric.type == "gauge"

    def test_interned_strings(self, monkeypatch):
        monkeypatch.setattr(
            python.sys, "getunicodeinternedsize", lambda: 1234, raising=False
        )
        (metric,) = by_name(collect(), "plone_python_interned_strings")
        assert metric.value == 1234

    def test_interned_strings_omitted_before_python_312(self, monkeypatch):
        monkeypatch.delattr(python.sys, "getunicodeinternedsize", raising=False)
        assert by_name(collect(), "plone_python_interned_strings") == []


class TestGCCounters:
    def test_counters_per_generation(self, monkeypatch):
        stats = [
            {"collections": 10, "collected": 100, "uncollectable": 0},
            {"collections": 2, "collected": 20, "uncollectable": 1},
            {"collections": 1, "collected": 5, "uncollectable": 3},
        ]
        monkeypatch.setattr(python.gc, "get_stats", lambda: stats)
        metrics = collect()
        collections = {
            m.labels["generation"]: m.value
            for m in by_name(metrics, "plone_gc_collections_total")
        }
        assert collections == {"0": 10, "1": 2, "2": 1}
        uncollectable = by_name(metrics, "plone_gc_uncollectable_total")
        assert [m.value for m in uncollectable] == [0, 1, 3]
        assert all(m.type == "counter" for m in uncollectable)
        assert len(by_name(metrics, "plone_gc_collected_total")) == 3


class TestGCPauses:
    def test_first_scrape_installs_one_callback(self):
        collect()
        collect()
        hooked = [cb for cb in gc.callbacks if cb == python._gc_pauses.callback]
        assert len(hooked) == 1

    def test_records_a_real_collection(self):
        collect()  # installs the callback
        gc.collect()
        metrics = collect()
        (count,) = by_name(metrics, "plone_gc_pause_seconds_count")
        (total,) = by_name(metrics, "plone_gc_pause_seconds_sum")
        assert count.value >= 1
        assert total.value > 0

    def test_histogram_buckets(self):
        tracker = python._gc_pauses
        ticks = iter([0.0, 0.0002, 1.0, 1.3])
        tracker.clock = lambda: next(ticks)
        tracker.callback("start", {"generation": 0})
        tracker.callback("stop", {"generation": 0})  # 0.2 ms
        tracker.callback("start", {"generation": 2})
        tracker.callback("stop", {"generation": 2})  # 300 ms
        buckets = {
            m.labels["le"]: m.value
            for m in by_name(collect(), "plone_gc_pause_seconds_bucket")
        }
        assert buckets["0.0001"] == 0
        assert buckets["0.0005"] == 1
        assert buckets["0.25"] == 1
        assert buckets["0.5"] == 2
        assert buckets["+Inf"] == 2

    def test_stop_without_start_is_ignored(self):
        # The callback can be installed while a collection is running.
        python._gc_pauses.callback("stop", {"generation": 0})
        (count,) = by_name(collect(), "plone_gc_pause_seconds_count")
        assert count.value == 0


class FakeMallInfo2:
    arena = 1000
    hblkhd = 2000
    uordblks = 3000
    fordblks = 4000


class TestMalloc:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("PLONE_OBSERVABILITY_MALLINFO", raising=False)
        names = {m.name for m in collect()}
        assert not any(name.startswith("plone_malloc_") for name in names)

    def test_reports_mallinfo2_fields(self, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        monkeypatch.setattr(python, "_mallinfo2", lambda: FakeMallInfo2())
        values = {
            m.name: m.value for m in collect() if m.name.startswith("plone_malloc_")
        }
        assert values == {
            "plone_malloc_inuse_bytes": 3000,
            "plone_malloc_free_bytes": 4000,
            "plone_malloc_mmap_bytes": 2000,
            "plone_malloc_arena_bytes": 1000,
        }

    def test_cached_for_ttl(self, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        calls = {"n": 0}

        def mallinfo2():
            calls["n"] += 1
            return FakeMallInfo2()

        monkeypatch.setattr(python, "_mallinfo2", mallinfo2)
        collect()
        collect()
        assert calls["n"] == 1

    def test_refreshed_after_ttl(self, monkeypatch):
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        monkeypatch.setenv("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "0")
        calls = {"n": 0}

        def mallinfo2():
            calls["n"] += 1
            return FakeMallInfo2()

        monkeypatch.setattr(python, "_mallinfo2", mallinfo2)
        collect()
        collect()
        assert calls["n"] == 2

    def test_omitted_without_mallinfo2(self, monkeypatch):
        # musl, macOS, glibc < 2.33
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        monkeypatch.setattr(python, "_mallinfo2", None)
        names = {m.name for m in collect()}
        assert not any(name.startswith("plone_malloc_") for name in names)

    def test_omitted_when_jemalloc_replaces_malloc(self, monkeypatch, caplog):
        # With jemalloc preloaded, glibc's mallinfo2() still resolves but
        # reports zeros; publishing them would be confidently wrong.
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        monkeypatch.setattr(python, "_mallinfo2", lambda: FakeMallInfo2())
        monkeypatch.setattr(python, "_jemalloc_active", True)
        with caplog.at_level("WARNING", logger=python.logger.name):
            collect()
            names = {m.name for m in collect()}
        assert not any(name.startswith("plone_malloc_") for name in names)
        warnings = [r for r in caplog.records if "jemalloc" in r.getMessage()]
        assert len(warnings) == 1  # logged once, not per scrape

    def test_no_jemalloc_warning_when_disabled(self, monkeypatch, caplog):
        monkeypatch.delenv("PLONE_OBSERVABILITY_MALLINFO", raising=False)
        monkeypatch.setattr(python, "_jemalloc_active", True)
        with caplog.at_level("WARNING", logger=python.logger.name):
            collect()
        assert not [r for r in caplog.records if "jemalloc" in r.getMessage()]

    @pytest.mark.skipif(
        not sys.platform.startswith("linux"), reason="glibc mallinfo2 on Linux"
    )
    def test_real_mallinfo2(self, monkeypatch):
        if python._mallinfo2 is None:
            pytest.skip("libc without mallinfo2")
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        values = {m.name: m.value for m in collect()}
        assert values["plone_malloc_inuse_bytes"] > 0
        assert values["plone_malloc_arena_bytes"] > 0


def test_load_mallinfo2_without_symbol(monkeypatch):
    monkeypatch.setattr(python.ctypes, "CDLL", lambda name: types.SimpleNamespace())
    assert python._load_mallinfo2() is None


def test_detect_jemalloc(monkeypatch):
    monkeypatch.setattr(
        python.ctypes, "CDLL", lambda name: types.SimpleNamespace(mallctl=object())
    )
    assert python._detect_jemalloc() is True


def test_detect_no_jemalloc(monkeypatch):
    monkeypatch.setattr(python.ctypes, "CDLL", lambda name: types.SimpleNamespace())
    assert python._detect_jemalloc() is False
