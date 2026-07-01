"""Per-span ZODB transfer-count attributes (objects loaded/stored).

Peeks ``ZODB.Connection.getTransferCounts(False)`` (no reset) at span start/end
and records the delta. The process-wide LoadStoreActivityMonitor resets only on
connection close (after spans end), so peeking here is non-disruptive.
"""

_LOADED_ATTR = "plone.zodb.objects_loaded"
_STORED_ATTR = "plone.zodb.objects_stored"
_LOAD_TIME_ATTR = "plone.zodb.load_time_ms"


def _connection(request):
    """The request's main ZODB connection, or None."""
    try:
        return request.PARENTS[-1]._p_jar
    except Exception:
        return None


def read_counts(request):
    """``(loads, stores, load_time_ns)`` peeked from the main connection, or None."""
    conn = _connection(request)
    if conn is None:
        return None
    try:
        loads, stores = conn.getTransferCounts(False)
    except Exception:
        return None
    return (loads, stores, getattr(conn, "_otel_load_time_ns", 0))


def annotate(span, before, after):
    """Set objects_loaded/stored on ``span`` from the ``after - before`` delta."""
    if span is None or before is None or after is None:
        return
    span.set_attribute(_LOADED_ATTR, after[0] - before[0])
    span.set_attribute(_STORED_ATTR, after[1] - before[1])
    span.set_attribute(_LOAD_TIME_ATTR, round((after[2] - before[2]) / 1_000_000, 3))
