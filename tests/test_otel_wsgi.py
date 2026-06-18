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
