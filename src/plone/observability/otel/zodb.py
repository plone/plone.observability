"""ZODB commit span via a transaction synchronizer (no monkeypatching)."""

from opentelemetry import trace

from plone.observability.otel.provider import TRACER_NAME
from plone.observability.otel.provider import is_enabled


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
        if not is_enabled():
            return
        tracer = trace.get_tracer(TRACER_NAME)
        self._spans[id(transaction)] = tracer.start_span("transaction.commit")

    def afterCompletion(self, transaction):
        span = self._spans.pop(id(transaction), None)
        if span is not None:
            span.end()


_synch = None


def register():
    global _synch
    if _synch is not None:
        return
    import transaction

    _synch = CommitTracer()
    transaction.manager.registerSynch(_synch)


def unregister():
    global _synch
    if _synch is None:
        return
    import transaction

    transaction.manager.unregisterSynch(_synch)
    _synch = None
