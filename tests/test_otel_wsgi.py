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


def test_make_filter_excludes_metrics_path(span_exporter):
    from plone.observability.otel.wsgi import make_filter

    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    wrapped = make_filter(app, {})
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/Plone/@@metrics",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.url_scheme": "http",
    }
    body = b"".join(wrapped(environ, lambda status, headers, exc=None: None))
    assert body == b"ok"
    # the scrape endpoint is excluded -> no WSGI server span at all
    spans = span_exporter.get_finished_spans()
    assert not any(s.kind.name == "SERVER" for s in spans)


def test_make_filter_activates_when_enabled(monkeypatch):
    from plone.observability.otel import catalog
    from plone.observability.otel import provider
    from plone.observability.otel import wsgi
    from plone.observability.otel import zodb

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
    from plone.observability.otel import provider
    from plone.observability.otel import wsgi

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "0")
    calls = []
    monkeypatch.setattr(provider, "setup_tracing", lambda: calls.append("setup"))
    wsgi.make_filter(object(), {})
    assert calls == []


def _server_span_name(span_exporter, method, path):
    from plone.observability.otel.wsgi import make_filter

    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.url_scheme": "http",
    }
    b"".join(make_filter(app, {})(environ, lambda status, headers, exc=None: None))
    return next(
        s.name for s in span_exporter.get_finished_spans() if s.kind.name == "SERVER"
    )


def test_server_span_name_has_no_path(span_exporter):
    # One name per URL would give span-to-metrics connectors one series per URL.
    path = (
        "/VirtualHostBase/https/example.org:443/Plone/VirtualHostRoot"
        "/++webresource++9ff7b2fc-bb60-5b7e-a094-49a1fe46d833/++plone++facetednavigation/faceted-edit.min.js"
    )
    assert _server_span_name(span_exporter, "GET", path) == "GET"


def test_server_span_name_of_unknown_method(span_exporter):
    assert _server_span_name(span_exporter, "FOO", "/Plone") == "HTTP"
