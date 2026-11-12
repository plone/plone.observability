def test_is_enabled_master_switch_on(monkeypatch):
    from plone.observability.otel import provider

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "1")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert provider.is_enabled() is True


def test_is_enabled_master_switch_off_overrides_endpoint(monkeypatch):
    from plone.observability.otel import provider

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_ENABLED", "false")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert provider.is_enabled() is False


def test_is_enabled_auto_on_with_endpoint(monkeypatch):
    from plone.observability.otel import provider

    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_ENABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert provider.is_enabled() is True


def test_is_enabled_off_by_default(monkeypatch):
    from plone.observability.otel import provider

    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert provider.is_enabled() is False


def test_setup_tracing_builds_provider_and_is_idempotent(monkeypatch):
    from plone.observability.otel import provider

    import opentelemetry.trace as trace

    monkeypatch.setattr(provider, "_ACTIVE", False)
    captured = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    provider.setup_tracing()
    provider.setup_tracing()  # second call must be a no-op
    assert len(captured) == 1
    assert captured[0] is not None


def _clear_protocol_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", raising=False)


def test_exporter_defaults_to_grpc(monkeypatch):
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from plone.observability.otel import provider

    _clear_protocol_env(monkeypatch)
    assert isinstance(provider._span_exporter(), OTLPSpanExporter)


def test_exporter_http_protobuf(monkeypatch):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from plone.observability.otel import provider

    _clear_protocol_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    assert isinstance(provider._span_exporter(), OTLPSpanExporter)


def test_traces_protocol_wins_over_general(monkeypatch):
    from plone.observability.otel import provider

    _clear_protocol_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
    assert provider._otlp_protocol() == "http/protobuf"


def test_explicit_grpc(monkeypatch):
    from plone.observability.otel import provider

    _clear_protocol_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", " GRPC ")
    assert provider._otlp_protocol() == "grpc"


def test_unsupported_protocol_falls_back_to_grpc(monkeypatch, caplog):
    # http/json is valid per the specification, but Python has no exporter.
    from plone.observability.otel import provider

    _clear_protocol_env(monkeypatch)
    monkeypatch.setattr(provider, "_warned_protocol", False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/json")
    with caplog.at_level("WARNING", logger=provider.logger.name):
        assert provider._otlp_protocol() == "grpc"
        assert provider._otlp_protocol() == "grpc"
    warnings = [r for r in caplog.records if "http/json" in r.getMessage()]
    assert len(warnings) == 1  # logged once


def test_setup_tracing_uses_selected_exporter(monkeypatch):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from plone.observability.otel import provider

    import opentelemetry.trace as trace

    _clear_protocol_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
    monkeypatch.setattr(provider, "_ACTIVE", False)
    captured = []
    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: captured.append(p))
    provider.setup_tracing()
    (tracer_provider,) = captured
    processors = tracer_provider._active_span_processor._span_processors
    assert isinstance(processors[0].span_exporter, OTLPSpanExporter)
