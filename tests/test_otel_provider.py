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
