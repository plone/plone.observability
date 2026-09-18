"""Tests for otel/instrumentors.py — optional OTel I/O instrumentors."""

import pytest


class _FakeInstrumentor:
    def __init__(self, fail=False):
        self.fail = fail
        self.instrumented = 0
        self.uninstrumented = 0

    def instrument(self, **kwargs):
        if self.fail:
            raise RuntimeError("nope")
        self.instrumented += 1

    def uninstrument(self, **kwargs):
        self.uninstrumented += 1


@pytest.fixture(autouse=True)
def _reset_instrumentors():
    yield
    from plone.observability.otel import instrumentors

    instrumentors.disable()


def test_switch_off_is_noop(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", raising=False)
    monkeypatch.setattr(instrumentors, "_load", lambda mp, cn: _FakeInstrumentor())
    instrumentors.enable()
    assert instrumentors._enabled == []


def test_switch_on_instruments_available_and_skips_missing(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "1")
    monkeypatch.setattr(instrumentors, "_target_installed", lambda name: True)
    fakes = {
        "BotocoreInstrumentor": _FakeInstrumentor(),
        "RequestsInstrumentor": _FakeInstrumentor(),
    }
    monkeypatch.setattr(instrumentors, "_load", lambda mp, cn: fakes.get(cn))

    instrumentors.enable()

    assert fakes["BotocoreInstrumentor"].instrumented == 1
    assert fakes["RequestsInstrumentor"].instrumented == 1
    assert set(instrumentors._enabled) == set(fakes.values())


def test_enable_is_idempotent(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "1")
    monkeypatch.setattr(instrumentors, "_target_installed", lambda name: True)
    fake = _FakeInstrumentor()
    monkeypatch.setattr(
        instrumentors,
        "_load",
        lambda mp, cn: fake if cn == "BotocoreInstrumentor" else None,
    )

    instrumentors.enable()
    instrumentors.enable()
    assert fake.instrumented == 1


def test_failing_instrumentor_is_skipped(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "1")
    monkeypatch.setattr(instrumentors, "_target_installed", lambda name: True)
    boom = _FakeInstrumentor(fail=True)
    ok = _FakeInstrumentor()
    mapping = {"BotocoreInstrumentor": boom, "RequestsInstrumentor": ok}
    monkeypatch.setattr(instrumentors, "_load", lambda mp, cn: mapping.get(cn))

    instrumentors.enable()  # must not raise

    assert ok.instrumented == 1
    assert boom not in instrumentors._enabled
    assert ok in instrumentors._enabled


def test_disable_uninstruments_and_allows_reenable(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "1")
    monkeypatch.setattr(instrumentors, "_target_installed", lambda name: True)
    fake = _FakeInstrumentor()
    monkeypatch.setattr(
        instrumentors,
        "_load",
        lambda mp, cn: fake if cn == "BotocoreInstrumentor" else None,
    )

    instrumentors.enable()
    instrumentors.disable()
    assert fake.uninstrumented == 1
    assert instrumentors._enabled == []

    instrumentors.enable()  # _done was reset
    assert fake.instrumented == 2


def test_switch_on_parses_env(monkeypatch):
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "true")
    assert instrumentors._switch_on() is True
    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "0")
    assert instrumentors._switch_on() is False
    monkeypatch.delenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", raising=False)
    assert instrumentors._switch_on() is False


def test_psycopg_is_supported():
    from plone.observability.otel import instrumentors

    assert (
        "psycopg",
        "opentelemetry.instrumentation.psycopg",
        "PsycopgInstrumentor",
    ) in instrumentors._SUPPORTED


def test_missing_target_library_is_skipped(monkeypatch):
    """The instrumentation package alone is not enough: the instrumented
    library itself must be importable, else the instrumentor is skipped."""
    from plone.observability.otel import instrumentors

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_INSTRUMENTORS", "1")
    fake = _FakeInstrumentor()
    monkeypatch.setattr(instrumentors, "_load", lambda mp, cn: fake)
    monkeypatch.setattr(
        instrumentors,
        "_target_installed",
        lambda name: name not in ("psycopg", "botocore"),
    )

    instrumentors.enable()

    assert fake.instrumented == len(instrumentors._SUPPORTED) - 2
