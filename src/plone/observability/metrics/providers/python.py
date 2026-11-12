from plone.base.utils import boolean_value
from plone.observability.interfaces import IMetricProvider
from plone.observability.metric import Metric
from zope.interface import implementer

import ctypes
import gc
import logging
import os
import sys
import threading
import time


logger = logging.getLogger(__name__)


# GC pauses are short: a young collection takes microseconds, a full one on a
# large heap can take a second.
GC_PAUSE_BUCKETS = (
    0.0001,
    0.0005,
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
)


class GCPauseTracker:
    """Histogram of garbage collection pauses, fed by a ``gc.callbacks`` hook.

    The callback runs inside the collector, which never runs two collections
    at once, so updates are serialized without a lock; taking one inside the
    collector could block it. A scrape may read a count and a sum from
    slightly different moments, which a histogram tolerates.
    """

    def __init__(self, buckets=GC_PAUSE_BUCKETS):
        self.buckets = buckets
        self.counts = [0] * (len(buckets) + 1)  # the last one is +Inf
        self.count = 0
        self.total = 0.0
        self.clock = time.perf_counter
        self._start = None
        self._install_lock = threading.Lock()
        self.installed = False

    def callback(self, phase, info):
        if phase == "start":
            self._start = self.clock()
            return
        if self._start is None:
            return  # installed during a collection
        duration = self.clock() - self._start
        self._start = None
        for i, bound in enumerate(self.buckets):
            if duration <= bound:
                self.counts[i] += 1
        self.counts[-1] += 1
        self.count += 1
        self.total += duration

    def install(self):
        if self.installed:
            return
        with self._install_lock:
            if not self.installed:
                gc.callbacks.append(self.callback)
                self.installed = True

    def uninstall(self):
        with self._install_lock:
            if self.installed:
                gc.callbacks.remove(self.callback)
                self.installed = False


# Installed on the first scrape, so pauses count from then on, like the ZODB
# load/store counters.
_gc_pauses = GCPauseTracker()


class _MallInfo2(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_size_t)
        for name in (
            "arena",
            "ordblks",
            "smblks",
            "hblks",
            "hblkhd",
            "usmblks",
            "fsmblks",
            "uordblks",
            "fordblks",
            "keepcost",
        )
    ]


def _load_mallinfo2():
    """Return glibc's ``mallinfo2()``, or None (musl, macOS, glibc < 2.33)."""
    try:
        func = ctypes.CDLL(None).mallinfo2
    except (AttributeError, OSError, TypeError):
        return None
    func.restype = _MallInfo2
    func.argtypes = []
    return func


_mallinfo2 = _load_mallinfo2()


def _detect_jemalloc():
    """Return True if jemalloc replaces malloc in this process.

    A jemalloc loaded with ``LD_PRELOAD`` exports ``mallctl`` into the global
    symbol namespace. glibc's ``mallinfo2()`` still resolves then, but reports
    zeros, because glibc no longer serves the allocations.
    """
    try:
        return hasattr(ctypes.CDLL(None), "mallctl")
    except (OSError, TypeError):
        return False


_jemalloc_active = _detect_jemalloc()
_warned_jemalloc = False

# mallinfo2() walks every free chunk while holding the arena lock: about
# 100 ns per chunk, so 100 ms on a heap fragmented into a million free chunks,
# while threads allocating from that arena wait. It is therefore opt-in and
# cached with the TTL shared with the other expensive metrics.
_malloc_cache = None  # (timestamp, {metric name: bytes})
_malloc_lock = threading.Lock()

_MALLOC_METRICS = (
    ("plone_malloc_inuse_bytes", "uordblks", "Bytes in use through glibc malloc"),
    (
        "plone_malloc_free_bytes",
        "fordblks",
        "Bytes glibc malloc holds but does not use (fragmentation)",
    ),
    ("plone_malloc_mmap_bytes", "hblkhd", "Bytes in large mmap'd malloc allocations"),
    ("plone_malloc_arena_bytes", "arena", "Bytes of the glibc malloc arenas"),
)


def _cache_ttl():
    return int(os.environ.get("PLONE_OBSERVABILITY_METRICS_CACHE_TTL", "60"))


def _malloc_enabled():
    return boolean_value(os.environ.get("PLONE_OBSERVABILITY_MALLINFO", "0"))


def _malloc_values():
    """Return the malloc gauges, from the cache while it is fresh."""
    global _malloc_cache
    now = time.time()
    with _malloc_lock:
        if _malloc_cache is not None and (now - _malloc_cache[0]) < _cache_ttl():
            return _malloc_cache[1]
    info = _mallinfo2()
    values = {name: getattr(info, field) for name, field, _ in _MALLOC_METRICS}
    with _malloc_lock:
        _malloc_cache = (now, values)
    return values


def _warn_jemalloc():
    global _warned_jemalloc
    if not _warned_jemalloc:
        logger.warning(
            "PLONE_OBSERVABILITY_MALLINFO is set, but jemalloc replaces glibc "
            "malloc in this process; leaving out the plone_malloc_* metrics, "
            "which would read zero"
        )
        _warned_jemalloc = True


@implementer(IMetricProvider)
class PythonMetricProvider:
    """Provides Python allocator, garbage collector and malloc metrics."""

    name = "python"
    scope = "instance"

    def __init__(self, context):
        self.context = context

    def collect(self):
        yield Metric(
            name="plone_python_allocated_blocks",
            value=sys.getallocatedblocks(),
            type="gauge",
            scope="instance",
            help="Memory blocks in use by the Python object allocator (pymalloc)",
        )

        # Python 3.12 and later.
        interned_size = getattr(sys, "getunicodeinternedsize", None)
        if interned_size is not None:
            yield Metric(
                name="plone_python_interned_strings",
                value=interned_size(),
                type="gauge",
                scope="instance",
                help="Number of interned strings",
            )

        yield from self._gc_counters()
        yield from self._gc_pauses()

        if _malloc_enabled() and _mallinfo2 is not None:
            if _jemalloc_active:
                _warn_jemalloc()
                return
            values = _malloc_values()
            for name, _, help_text in _MALLOC_METRICS:
                yield Metric(
                    name=name,
                    value=values[name],
                    type="gauge",
                    scope="instance",
                    help=help_text,
                )

    def _gc_counters(self):
        stats = gc.get_stats()
        for key, name, help_text in (
            ("collections", "plone_gc_collections_total", "Garbage collections"),
            ("collected", "plone_gc_collected_total", "Objects collected by the GC"),
            (
                "uncollectable",
                "plone_gc_uncollectable_total",
                "Uncollectable objects found by the GC",
            ),
        ):
            for generation, gen_stats in enumerate(stats):
                yield Metric(
                    name=name,
                    value=gen_stats[key],
                    type="counter",
                    scope="instance",
                    help=help_text,
                    labels={"generation": str(generation)},
                )

    def _gc_pauses(self):
        tracker = _gc_pauses
        tracker.install()
        yield Metric(
            name="plone_gc_pause_seconds_sum",
            value=round(tracker.total, 6),
            type="counter",
            scope="instance",
            help="Total time spent in garbage collection in seconds",
        )
        yield Metric(
            name="plone_gc_pause_seconds_count",
            value=tracker.count,
            type="counter",
            scope="instance",
            help="Number of garbage collections timed (histogram count)",
        )
        bounds = [str(bound) for bound in tracker.buckets] + ["+Inf"]
        for le, count in zip(bounds, list(tracker.counts), strict=True):
            yield Metric(
                name="plone_gc_pause_seconds_bucket",
                value=count,
                type="counter",
                scope="instance",
                help="Garbage collection pause histogram bucket",
                labels={"le": le},
            )
