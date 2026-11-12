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


# The real mallctl when the suite runs with jemalloc preloaded (CI job
# "Python 3.12 (jemalloc)"), else None. Saved before the fixture replaces it.
REAL_MALLCTL = python._mallctl


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """The GC pause tracker and the malloc cache are module-level; give every
    test a fresh tracker and an empty cache, and unhook the GC callback."""
    monkeypatch.setattr(python, "_gc_pauses", python.GCPauseTracker())
    monkeypatch.setattr(python, "_malloc_cache", None)
    monkeypatch.setattr(python, "_jemalloc_active", False)
    monkeypatch.setattr(python, "_warned_jemalloc", False)
    monkeypatch.setattr(python, "_mallctl", None)
    monkeypatch.setattr(python, "_warned_jemalloc_stats", False)
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
        if REAL_MALLCTL is not None:
            pytest.skip("jemalloc replaces glibc malloc")
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        values = {m.name: m.value for m in collect()}
        assert values["plone_malloc_inuse_bytes"] > 0
        assert values["plone_malloc_arena_bytes"] > 0


def test_load_mallinfo2_without_symbol(monkeypatch):
    monkeypatch.setattr(python.ctypes, "CDLL", lambda name: types.SimpleNamespace())
    assert python._load_mallinfo2() is None


def test_load_mallctl(monkeypatch):
    mallctl = types.SimpleNamespace()
    monkeypatch.setattr(
        python.ctypes, "CDLL", lambda name: types.SimpleNamespace(mallctl=mallctl)
    )
    assert python._load_mallctl() is mallctl
    assert mallctl.restype is python.ctypes.c_int


def test_load_mallctl_without_jemalloc(monkeypatch):
    monkeypatch.setattr(python.ctypes, "CDLL", lambda name: types.SimpleNamespace())
    assert python._load_mallctl() is None


class FakeMallctl:
    """Answers like jemalloc's mallctl(): writes into the byref() buffers and
    returns 0, or ENOENT (2) for names it does not know."""

    def __init__(self, stats=None, epoch_rc=0):
        self.stats = {
            "stats.allocated": 100,
            "stats.active": 160,
            "stats.metadata": 10,
            "stats.resident": 200,
            "stats.mapped": 300,
            "stats.retained": 400,
        }
        if stats is not None:
            self.stats = stats
        self.epoch_rc = epoch_rc
        self.epochs = 0

    def __call__(self, name, oldp, oldlenp, newp, newlen):
        name = name.decode()
        if name == "epoch":
            self.epochs += 1
            return self.epoch_rc
        if name not in self.stats:
            return 2
        oldp._obj.value = self.stats[name]
        return 0


def jemalloc_values(metrics):
    return {m.name: m.value for m in metrics if m.name.startswith("plone_jemalloc_")}


class TestJemalloc:
    def test_absent_without_jemalloc(self):
        assert jemalloc_values(collect()) == {}

    def test_reports_stats(self, monkeypatch):
        monkeypatch.setattr(python, "_mallctl", FakeMallctl())
        assert jemalloc_values(collect()) == {
            "plone_jemalloc_allocated_bytes": 100,
            "plone_jemalloc_active_bytes": 160,
            "plone_jemalloc_metadata_bytes": 10,
            "plone_jemalloc_resident_bytes": 200,
            "plone_jemalloc_mapped_bytes": 300,
            "plone_jemalloc_retained_bytes": 400,
        }

    def test_refreshes_stats_on_every_scrape(self, monkeypatch):
        # jemalloc caches its statistics until "epoch" is written.
        mallctl = FakeMallctl()
        monkeypatch.setattr(python, "_mallctl", mallctl)
        collect()
        collect()
        assert mallctl.epochs == 2

    def test_on_without_opt_in(self, monkeypatch):
        monkeypatch.delenv("PLONE_OBSERVABILITY_MALLINFO", raising=False)
        monkeypatch.setattr(python, "_mallctl", FakeMallctl())
        assert jemalloc_values(collect())

    def test_gauges_with_instance_scope(self, monkeypatch):
        monkeypatch.setattr(python, "_mallctl", FakeMallctl())
        metrics = [m for m in collect() if m.name.startswith("plone_jemalloc_")]
        assert {(m.type, m.scope) for m in metrics} == {("gauge", "instance")}

    def test_build_without_stats(self, monkeypatch, caplog):
        # --disable-stats: the stats.* names do not exist.
        monkeypatch.setattr(python, "_mallctl", FakeMallctl(stats={}))
        with caplog.at_level("WARNING", logger=python.logger.name):
            collect()
            assert jemalloc_values(collect()) == {}
        warnings = [r for r in caplog.records if "statistics" in r.getMessage()]
        assert len(warnings) == 1  # logged once

    def test_failed_epoch(self, monkeypatch):
        monkeypatch.setattr(python, "_mallctl", FakeMallctl(epoch_rc=14))
        assert jemalloc_values(collect()) == {}

    def test_mallinfo_warning_points_to_jemalloc_metrics(self, monkeypatch, caplog):
        monkeypatch.setenv("PLONE_OBSERVABILITY_MALLINFO", "1")
        monkeypatch.setattr(python, "_mallinfo2", lambda: FakeMallInfo2())
        monkeypatch.setattr(python, "_jemalloc_active", True)
        with caplog.at_level("WARNING", logger=python.logger.name):
            collect()
        (record,) = [r for r in caplog.records if "MALLINFO" in r.getMessage()]
        assert "plone_jemalloc_" in record.getMessage()

    @pytest.mark.skipif(REAL_MALLCTL is None, reason="needs jemalloc preloaded")
    def test_real_jemalloc(self, monkeypatch):
        monkeypatch.setattr(python, "_mallctl", REAL_MALLCTL)
        keep = [bytearray(1024 * 1024) for _ in range(8)]
        values = jemalloc_values(collect())
        assert values["plone_jemalloc_allocated_bytes"] >= 8 * 1024 * 1024
        assert (
            values["plone_jemalloc_active_bytes"]
            >= values["plone_jemalloc_allocated_bytes"]
        )
        del keep
