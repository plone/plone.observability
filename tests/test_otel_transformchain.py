class FakeRequest:
    """plone.transformchain handlers only need request.environ."""

    def __init__(self):
        self.environ = {}


class FakeHandler:
    pass


class Ev:
    """Stand-in for the transformchain event objects (request/name/handler)."""

    def __init__(self, request, name=None, handler=None):
        self.request = request
        self.name = name
        self.handler = handler


def _run_chain(tc, req, names):
    """Drive a full, successful chain over the given transform names."""
    tc.on_before_transforms(Ev(req))
    for name in names:
        tc.on_before_single_transform(Ev(req, name=name, handler=FakeHandler()))
        tc.on_after_single_transform(Ev(req, name=name, handler=FakeHandler()))
    tc.on_after_transforms(Ev(req))


def test_emits_chain_span_and_one_child_per_transform(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    _run_chain(tc, req, ["theme", "gzip"])

    spans = span_exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "transformchain" in names
    assert "transform.theme" in names
    assert "transform.gzip" in names


def test_child_spans_nest_under_the_chain_span(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    _run_chain(tc, req, ["theme"])

    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    chain = spans["transformchain"]
    child = spans["transform.theme"]
    assert child.parent is not None
    assert child.parent.span_id == chain.context.span_id


def test_child_span_carries_name_and_handler_attributes(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    _run_chain(tc, req, ["theme"])

    child = next(
        s for s in span_exporter.get_finished_spans() if s.name == "transform.theme"
    )
    assert child.attributes["plone.transform.name"] == "theme"
    assert child.attributes["plone.transform.handler"] == "FakeHandler"


def test_chain_span_records_transform_count(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    _run_chain(tc, req, ["theme", "gzip", "caching"])

    chain = next(
        s for s in span_exporter.get_finished_spans() if s.name == "transformchain"
    )
    assert chain.attributes["plone.transformchain.transform_count"] == 3


def test_noop_when_disabled(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    _run_chain(tc, req, ["theme"])
    assert span_exporter.get_finished_spans() == ()


def test_flush_on_request_end_closes_spans_left_open_by_a_raising_transform(
    span_exporter, monkeypatch
):
    """A transform that raises makes the Transformer swallow the error and skip
    AfterSingleTransform/AfterTransforms; the request still ends in success, so
    the request-end flush must close the dangling spans."""
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    tc.on_before_transforms(Ev(req))
    tc.on_before_single_transform(Ev(req, name="theme", handler=FakeHandler()))
    # transform raised -> no after_single / after_transforms; request succeeds:
    tc.on_pub_success(Ev(req))

    names = [s.name for s in span_exporter.get_finished_spans()]
    assert "transformchain" in names
    assert "transform.theme" in names
    # nothing left dangling on the request
    assert not [k for k in req.environ if k.startswith("plone.observability.otel")]


def test_noop_when_suppressed(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import exclusions
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    token = exclusions.suppress_token()
    try:
        _run_chain(tc, req, ["theme"])
    finally:
        exclusions.detach(token)
    assert span_exporter.get_finished_spans() == ()


def test_handlers_are_safe_when_chain_never_started(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import transformchain as tc

    req = FakeRequest()
    # No on_before_transforms; these must not raise and must emit nothing.
    tc.on_before_single_transform(Ev(req, name="theme", handler=FakeHandler()))
    tc.on_after_single_transform(Ev(req, name="theme", handler=FakeHandler()))
    tc.on_after_transforms(Ev(req))
    tc.on_pub_success(Ev(req))
    assert span_exporter.get_finished_spans() == ()
