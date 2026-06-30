import pytest


@pytest.fixture(autouse=True)
def _clean_env_and_cache(monkeypatch):
    from plone.observability.otel import exclusions

    for var in (
        "OTEL_PYTHON_WSGI_EXCLUDED_URLS",
        "OTEL_PYTHON_EXCLUDED_URLS",
        "PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS",
    ):
        monkeypatch.delenv(var, raising=False)
    exclusions.reset_cache()
    yield
    exclusions.reset_cache()


def test_metrics_excluded_by_default():
    from plone.observability.otel import exclusions

    assert exclusions.is_excluded("/Plone/@@metrics") is True
    assert exclusions.is_excluded("/@@metrics") is True


def test_normal_path_not_excluded_by_default():
    from plone.observability.otel import exclusions

    assert exclusions.is_excluded("/Plone/front-page") is False
    assert exclusions.is_excluded("") is False


def test_env_excluded_urls_add_patterns(monkeypatch):
    from plone.observability.otel import exclusions

    monkeypatch.setenv("OTEL_PYTHON_WSGI_EXCLUDED_URLS", "healthz,ping")
    exclusions.reset_cache()
    assert exclusions.is_excluded("/healthz") is True
    assert exclusions.is_excluded("/api/ping") is True
    # default still applies alongside env patterns
    assert exclusions.is_excluded("/@@metrics") is True


def test_generic_env_var_is_fallback(monkeypatch):
    from plone.observability.otel import exclusions

    monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", "healthz")
    exclusions.reset_cache()
    assert exclusions.is_excluded("/healthz") is True


def test_wsgi_specific_env_var_wins_over_generic(monkeypatch):
    from plone.observability.otel import exclusions

    monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", "generic")
    monkeypatch.setenv("OTEL_PYTHON_WSGI_EXCLUDED_URLS", "specific")
    exclusions.reset_cache()
    assert exclusions.is_excluded("/specific") is True
    assert exclusions.is_excluded("/generic") is False


def test_defaults_can_be_disabled(monkeypatch):
    from plone.observability.otel import exclusions

    monkeypatch.setenv("PLONE_OBSERVABILITY_OTEL_EXCLUDE_DEFAULTS", "0")
    exclusions.reset_cache()
    assert exclusions.is_excluded("/@@metrics") is False


def test_suppression_context_round_trip():
    from plone.observability.otel import exclusions

    assert exclusions.is_suppressed() is False
    token = exclusions.suppress_token()
    try:
        assert exclusions.is_suppressed() is True
    finally:
        exclusions.detach(token)
    assert exclusions.is_suppressed() is False


def test_detach_tolerates_none():
    from plone.observability.otel import exclusions

    # no-op, must not raise
    exclusions.detach(None)
