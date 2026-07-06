"""Per-span ZODB transfer-count attributes (objects loaded/stored).

Peeks ``ZODB.Connection.getTransferCounts(False)`` (no reset) at span start/end
and records the delta. The process-wide LoadStoreActivityMonitor resets only on
connection close (after spans end), so peeking here is non-disruptive.
"""

_LOADED_ATTR = "plone.zodb.objects_loaded"
_STORED_ATTR = "plone.zodb.objects_stored"
_LOAD_TIME_ATTR = "plone.zodb.load_time_ms"
# zodb-pgjsonb exposes per-connection load counters (plain ints, no dependency
# on this package).  When present they split objects_loaded three ways: shared-
# cache (L2) hits, objects fetched from PostgreSQL, and the number of PostgreSQL
# round-trips (queries).  So a slow span can be attributed to a cold/gated cache
# (all PG) vs high per-load latency (few PG, but slow), and load_pg_objects /
# load_pg_queries gives objects-per-round-trip (~1 = N+1, >>1 = batched/prefetch).
# Other storages don't have them; the getattr defaults keep this a no-op there.
_L2_HITS_ATTR = "plone.zodb.load_l2_hits"
_PG_OBJECTS_ATTR = "plone.zodb.load_pg_objects"
_PG_QUERIES_ATTR = "plone.zodb.load_pg_queries"


def _connection(request):
    """The request's main ZODB connection, or None."""
    try:
        return request.PARENTS[-1]._p_jar
    except Exception:
        return None


def read_counts(request):
    """``(loads, stores, load_time_ns, l2_hits, pg_objects, pg_queries)`` peeked
    from the main connection, or None.  ``l2_hits``/``pg_objects``/``pg_queries``
    are 0 on storages that don't expose zodb-pgjsonb's per-connection load
    counters."""
    conn = _connection(request)
    if conn is None:
        return None
    try:
        loads, stores = conn.getTransferCounts(False)
    except Exception:
        return None
    instance = getattr(conn, "_storage", None)
    l2_hits = getattr(instance, "_l2_load_hits", 0)
    pg_objects = getattr(instance, "_pg_load_count", 0)
    pg_queries = getattr(instance, "_pg_query_count", 0)
    return (
        loads,
        stores,
        getattr(conn, "_otel_load_time_ns", 0),
        l2_hits,
        pg_objects,
        pg_queries,
    )


def annotate(span, before, after):
    """Set the ZODB per-span attributes from the ``after - before`` delta."""
    if span is None or before is None or after is None:
        return
    span.set_attribute(_LOADED_ATTR, after[0] - before[0])
    span.set_attribute(_STORED_ATTR, after[1] - before[1])
    span.set_attribute(_LOAD_TIME_ATTR, round((after[2] - before[2]) / 1_000_000, 3))
    span.set_attribute(_L2_HITS_ATTR, after[3] - before[3])
    span.set_attribute(_PG_OBJECTS_ATTR, after[4] - before[4])
    span.set_attribute(_PG_QUERIES_ATTR, after[5] - before[5])
