from ZPublisher.pubevents import PubAfterTraversal
from ZPublisher.pubevents import PubFailure
from ZPublisher.pubevents import PubStart
from ZPublisher.pubevents import PubSuccess


class FakeRequest:
    """Minimal request: pubevents need .environ and .get()."""

    def __init__(self, path="/foo"):
        self.environ = {}
        self._data = {"PATH_INFO": path}

    def get(self, key, default=None):
        return self._data.get(key, default)


def test_successful_publish_emits_span(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import pubevents

    req = FakeRequest("/news")
    pubevents.on_pub_start(PubStart(req))
    pubevents.on_after_traversal(PubAfterTraversal(req))
    pubevents.on_pub_success(PubSuccess(req))

    spans = span_exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert "ZPublisher.publish" in names
    publish = next(s for s in spans if s.name == "ZPublisher.publish")
    assert publish.attributes["http.route"] == "/news"
    assert publish.status.status_code.name in ("OK", "UNSET")


def test_failed_publish_marks_span_error(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import pubevents

    req = FakeRequest("/boom")
    pubevents.on_pub_start(PubStart(req))
    try:
        raise ValueError("kaboom")
    except ValueError:
        import sys

        pubevents.on_pub_failure(PubFailure(req, sys.exc_info(), False))

    spans = span_exporter.get_finished_spans()
    publish = next(s for s in spans if s.name == "ZPublisher.publish")
    assert publish.status.status_code.name == "ERROR"


def test_publish_noop_when_disabled(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    from plone.observability.otel import pubevents

    req = FakeRequest("/x")
    pubevents.on_pub_start(PubStart(req))
    pubevents.on_pub_success(PubSuccess(req))
    assert span_exporter.get_finished_spans() == ()


def test_excluded_path_emits_no_publish_span(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import pubevents

    req = FakeRequest("/Plone/@@metrics")
    pubevents.on_pub_start(PubStart(req))
    pubevents.on_after_traversal(PubAfterTraversal(req))
    pubevents.on_pub_success(PubSuccess(req))
    assert span_exporter.get_finished_spans() == ()


def test_excluded_path_marks_suppressed_during_request(monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    from plone.observability.otel import exclusions
    from plone.observability.otel import pubevents

    req = FakeRequest("/@@metrics")
    pubevents.on_pub_start(PubStart(req))
    try:
        # subscribers running during the request see suppression
        assert exclusions.is_suppressed() is True
    finally:
        pubevents.on_pub_success(PubSuccess(req))
    # context restored after the request
    assert exclusions.is_suppressed() is False


def _auth_user(monkeypatch, name="alice", uid="alice-id"):
    from plone.observability import auth

    class _User:
        def getUserName(self):
            return name

        def getId(self):
            return uid

    class _SM:
        def getUser(self):
            return _User()

    monkeypatch.setattr(auth, "getSecurityManager", lambda: _SM())


def test_span_sets_authenticated_attribute(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_USER_ID", raising=False)
    _auth_user(monkeypatch)
    from plone.observability.otel import pubevents

    req = FakeRequest("/x")
    pubevents.on_pub_start(PubStart(req))
    pubevents.on_pub_success(PubSuccess(req))

    span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "ZPublisher.publish"
    )
    assert span.attributes["enduser.authenticated"] is True
    assert "enduser.id" not in span.attributes  # opt-in is off


def test_span_includes_user_id_when_opted_in(span_exporter, monkeypatch):
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_USER_ID", "1")
    _auth_user(monkeypatch)
    from plone.observability.otel import pubevents

    req = FakeRequest("/x")
    pubevents.on_pub_start(PubStart(req))
    pubevents.on_pub_success(PubSuccess(req))

    span = next(
        s for s in span_exporter.get_finished_spans() if s.name == "ZPublisher.publish"
    )
    assert span.attributes["enduser.id"] == "alice-id"
