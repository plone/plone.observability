from plone.observability.metrics.access import is_allowed
from unittest import mock

import os


class TestIsAllowed:
    def test_no_allowlist_allows_all(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_allowed("1.2.3.4", {}) is True

    def test_allowlist_allows_matching(self):
        env = {"PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_allowed("10.1.2.3", {}) is True

    def test_allowlist_blocks_non_matching(self):
        env = {"PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_allowed("192.168.1.1", {}) is False

    def test_multiple_cidrs(self):
        env = {"PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8,192.168.0.0/16"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_allowed("192.168.1.1", {}) is True
            assert is_allowed("172.16.0.1", {}) is False

    def test_forwarded_for_with_trusted_proxy(self):
        env = {
            "PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8",
            "PLONE_OBSERVABILITY_TRUSTED_PROXIES": "127.0.0.1",
        }
        headers = {"X-Forwarded-For": "10.1.2.3, 127.0.0.1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_allowed("127.0.0.1", headers) is True

    def test_forwarded_for_with_untrusted_proxy(self):
        env = {
            "PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8",
            "PLONE_OBSERVABILITY_TRUSTED_PROXIES": "127.0.0.1",
        }
        headers = {"X-Forwarded-For": "10.1.2.3"}
        with mock.patch.dict(os.environ, env, clear=True):
            # Peer is not trusted, so X-Forwarded-For is ignored
            assert is_allowed("192.168.1.1", headers) is False

    def test_forwarded_for_spoofing_blocked(self):
        env = {
            "PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8",
            "PLONE_OBSERVABILITY_TRUSTED_PROXIES": "127.0.0.1",
        }
        # Attacker sends X-Forwarded-For but connects directly
        headers = {"X-Forwarded-For": "10.1.2.3"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_allowed("evil.attacker.com", headers) is False

    def test_default_trusted_proxies(self):
        env = {
            "PLONE_OBSERVABILITY_METRICS_ALLOWLIST": "10.0.0.0/8",
        }
        headers = {"X-Forwarded-For": "10.1.2.3"}
        with mock.patch.dict(os.environ, env, clear=True):
            # 127.0.0.1 is trusted by default
            assert is_allowed("127.0.0.1", headers) is True
