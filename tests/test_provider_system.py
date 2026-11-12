from plone.observability.interfaces import IMetricProvider
from plone.observability.metrics.providers.system import SystemMetricProvider
from zope.interface.verify import verifyObject

import os
import pytest
import resource
import types


class FakeApp:
    pass


def _fix_rusage(monkeypatch, ru_maxrss):
    """Pin getrusage(): the peak RSS can grow between the provider's call and
    a second one in the test, so comparing against a live read is racy."""
    usage = types.SimpleNamespace(ru_maxrss=ru_maxrss, ru_utime=1.0, ru_stime=0.5)
    monkeypatch.setattr(resource, "getrusage", lambda who: usage)


class TestSystemMetricProvider:
    def test_implements_interface(self):
        provider = SystemMetricProvider(FakeApp())
        assert verifyObject(IMetricProvider, provider)

    def test_scope_is_instance(self):
        provider = SystemMetricProvider(FakeApp())
        assert provider.scope == "instance"

    def test_collects_rss_metric(self):
        provider = SystemMetricProvider(FakeApp())
        metrics = list(provider.collect())
        names = [m.name for m in metrics]
        assert "plone_process_rss_bytes" in names

    def test_collects_cpu_metric(self):
        provider = SystemMetricProvider(FakeApp())
        metrics = list(provider.collect())
        names = [m.name for m in metrics]
        assert "plone_process_cpu_seconds" in names

    def test_rss_is_positive(self):
        provider = SystemMetricProvider(FakeApp())
        metrics = {m.name: m for m in provider.collect()}
        assert metrics["plone_process_rss_bytes"].value > 0

    def test_rss_reads_resident_pages_from_statm(self, tmp_path, monkeypatch):
        from plone.observability.metrics.providers import system

        statm = tmp_path / "statm"
        statm.write_text("5000 1234 300 10 0 900 0\n")
        monkeypatch.setattr(system, "_STATM", str(statm))
        metrics = {m.name: m for m in SystemMetricProvider(FakeApp()).collect()}
        page_size = os.sysconf("SC_PAGE_SIZE")
        assert metrics["plone_process_rss_bytes"].value == 1234 * page_size

    def test_rss_omitted_without_statm(self, tmp_path, monkeypatch):
        """Without /proc there is no current RSS. Reporting the peak under
        the current name would be wrong, so the metric is left out."""
        from plone.observability.metrics.providers import system

        monkeypatch.setattr(system, "_STATM", str(tmp_path / "missing"))
        names = [m.name for m in SystemMetricProvider(FakeApp()).collect()]
        assert "plone_process_rss_bytes" not in names
        assert "plone_process_rss_peak_bytes" in names

    def test_rss_split_reads_anon_and_file_from_status(self, tmp_path, monkeypatch):
        from plone.observability.metrics.providers import system

        status = tmp_path / "status"
        status.write_text(
            "Name:\tpython\n"
            "VmRSS:\t  300 kB\n"
            "RssAnon:\t  200 kB\n"
            "RssFile:\t   90 kB\n"
            "RssShmem:\t   10 kB\n"
        )
        monkeypatch.setattr(system, "_STATUS", str(status))
        metrics = {m.name: m for m in SystemMetricProvider(FakeApp()).collect()}
        assert metrics["plone_process_rss_anon_bytes"].value == 200 * 1024
        assert metrics["plone_process_rss_file_bytes"].value == 90 * 1024
        assert metrics["plone_process_rss_anon_bytes"].type == "gauge"

    def test_rss_split_omitted_without_status(self, tmp_path, monkeypatch):
        from plone.observability.metrics.providers import system

        monkeypatch.setattr(system, "_STATUS", str(tmp_path / "missing"))
        names = [m.name for m in SystemMetricProvider(FakeApp()).collect()]
        assert "plone_process_rss_anon_bytes" not in names
        assert "plone_process_rss_file_bytes" not in names

    def test_rss_split_omitted_when_fields_missing(self, tmp_path, monkeypatch):
        # Kernels before 4.5 have VmRSS but no RssAnon/RssFile.
        from plone.observability.metrics.providers import system

        status = tmp_path / "status"
        status.write_text("Name:\tpython\nVmRSS:\t  300 kB\n")
        monkeypatch.setattr(system, "_STATUS", str(status))
        names = [m.name for m in SystemMetricProvider(FakeApp()).collect()]
        assert "plone_process_rss_anon_bytes" not in names

    def test_rss_peak_is_ru_maxrss_in_kib_on_linux(self, monkeypatch):
        from plone.observability.metrics.providers import system

        monkeypatch.setattr(system.sys, "platform", "linux")
        _fix_rusage(monkeypatch, ru_maxrss=144760)
        metrics = {m.name: m for m in SystemMetricProvider(FakeApp()).collect()}
        assert metrics["plone_process_rss_peak_bytes"].value == 144760 * 1024
        assert metrics["plone_process_rss_peak_bytes"].type == "gauge"

    def test_rss_peak_is_ru_maxrss_in_bytes_on_macos(self, monkeypatch):
        from plone.observability.metrics.providers import system

        monkeypatch.setattr(system.sys, "platform", "darwin")
        _fix_rusage(monkeypatch, ru_maxrss=148234240)
        metrics = {m.name: m for m in SystemMetricProvider(FakeApp()).collect()}
        assert metrics["plone_process_rss_peak_bytes"].value == 148234240

    @pytest.mark.skipif(
        not os.path.exists("/proc/self/statm"), reason="needs /proc/self/statm"
    )
    def test_rss_goes_down_when_memory_is_freed(self):
        """Regression for #81: the gauge reported ru_maxrss and never fell."""

        def rss():
            metrics = {m.name: m for m in SystemMetricProvider(FakeApp()).collect()}
            return metrics["plone_process_rss_bytes"].value

        size = 256 * 1024 * 1024
        before = rss()
        blob = bytearray(size)  # zero-filled, so every page is touched
        during = rss()
        del blob
        after = rss()
        assert during - before > size // 2
        assert during - after > size // 2

    def test_all_metrics_are_instance_scope(self):
        provider = SystemMetricProvider(FakeApp())
        for m in provider.collect():
            assert m.scope == "instance"
