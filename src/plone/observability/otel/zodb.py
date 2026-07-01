"""ZODB commit span (transaction synchronizer) + per-load time accumulation.

The commit span uses a synchronizer (no monkeypatching). The per-load time is
collected by wrapping ``Connection.setstate`` -- the one storage-agnostic load
chokepoint -- and accumulating the elapsed nanoseconds on the connection
(``_otel_load_time_ns``), which ``otel/dbcounts.py`` reads as a per-span delta.
"""

from opentelemetry import trace
from plone.observability.otel import exclusions
from plone.observability.otel.provider import is_enabled
from plone.observability.otel.provider import TRACER_NAME

import time


class CommitTracer:
    """ISynchronizer that spans transaction completion.

    beforeCompletion/afterCompletion bracket the commit (or abort). The span is
    keyed by transaction identity so concurrent managers do not collide.
    """

    def __init__(self):
        self._spans = {}

    def newTransaction(self, transaction):
        pass

    def beforeCompletion(self, transaction):
        if not is_enabled() or exclusions.is_suppressed():
            return
        tracer = trace.get_tracer(TRACER_NAME)
        self._spans[id(transaction)] = tracer.start_span("transaction.commit")

    def afterCompletion(self, transaction):
        span = self._spans.pop(id(transaction), None)
        if span is not None:
            span.end()


_synch = None
_setstate_patched = []


def _traced_setstate(original):
    """Wrap Connection.setstate to accumulate load time on the connection.

    Timed unconditionally (no per-call is_enabled/suppressed check): setstate
    runs thousands of times per request, the patch is only installed while
    tracing is active, and the delta is read only at real spans.
    """

    def setstate(self, obj):
        start = time.perf_counter_ns()
        try:
            return original(self, obj)
        finally:
            self._otel_load_time_ns = (
                getattr(self, "_otel_load_time_ns", 0) + time.perf_counter_ns() - start
            )

    return setstate


def _patch_setstate():
    from ZODB.Connection import Connection

    original = Connection.setstate
    if getattr(original, "_otel_wrapped", False):
        return
    wrapper = _traced_setstate(original)
    wrapper._otel_wrapped = True
    wrapper._otel_original = original
    Connection.setstate = wrapper
    _setstate_patched.append((Connection, original))


def _unpatch_setstate():
    while _setstate_patched:
        cls, original = _setstate_patched.pop()
        cls.setstate = original


def register():
    global _synch
    _patch_setstate()
    if _synch is None:
        import transaction

        _synch = CommitTracer()
        transaction.manager.registerSynch(_synch)


def unregister():
    global _synch
    _unpatch_setstate()
    if _synch is not None:
        import transaction

        transaction.manager.unregisterSynch(_synch)
        _synch = None
