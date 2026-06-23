def test_make_filter_creates_server_span(span_exporter):
    from plone.observability.otel.wsgi import make_filter

    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    wrapped = make_filter(app, {})
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.url_scheme": "http",
    }
    body = b"".join(wrapped(environ, lambda status, headers, exc=None: None))
    assert body == b"ok"

    spans = span_exporter.get_finished_spans()
    assert any(s.kind.name == "SERVER" for s in spans)


def test_make_filter_activates_when_enabled(monkeypatch):
    from plone.observability.otel import catalog, provider, wsgi, zodb

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    monkeypatch.setattr(zodb, "register", lambda: calls.append("zodb"))
    monkeypatch.setattr(catalog, "instrument_catalog", lambda: calls.append("catalog"))

    app = object()
    wrapped = wsgi.make_filter(app, {})
    assert calls == ["setup", "zodb", "catalog"]
    assert wrapped is not app  # wrapped by OpenTelemetryMiddleware


def test_make_filter_skips_activation_when_disabled(monkeypatch):
    from plone.observability.otel import provider, wsgi

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    wsgi.make_filter(object(), {})
    assert calls == []
