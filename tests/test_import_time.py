"""The WSGI filter modules must not import Zope or Plone when PasteDeploy loads them (#105).

PasteDeploy imports the filter entry points while it builds the pipeline, before it
calls the Zope app factory that applies zope.conf. A module imported then keeps
what it read at import time: ``OFS.ObjectManager.CONFIG`` the default configuration,
``chameleon.config`` the environment without zope.conf's ``<environment>`` block.
The filter factories run after the app factory, so they may import what they need.

Both tests run in a fresh interpreter: in the test process these modules are loaded
long before any test runs.
"""

from importlib.metadata import entry_points

import pytest
import subprocess
import sys
import textwrap


# Modules that read the Zope configuration or the environment at import time, and the
# packages that lead to them.
FORBIDDEN = ("OFS", "Products", "App", "chameleon", "zope.i18n", "plone.base")

FILTERS = sorted(
    ep.name
    for ep in entry_points(group="paste.filter_app_factory")
    if ep.value.startswith("plone.observability.")
)


def run(code, **kwargs):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
        **kwargs,
    )


def test_all_filters_are_checked():
    assert FILTERS == ["healthserver", "observability", "opentelemetry"]


@pytest.mark.parametrize("name", FILTERS)
def test_loading_a_filter_imports_no_zope_or_plone(name):
    result = run(
        f"""
        import sys
        from importlib.metadata import entry_points

        (ep,) = [e for e in entry_points(group="paste.filter_app_factory")
                 if e.name == {name!r} and e.value.startswith("plone.observability.")]
        ep.load()
        forbidden = {FORBIDDEN!r}
        loaded = sorted(m for m in sys.modules
                        if any(m == f or m.startswith(f + ".") for f in forbidden))
        print("\\n".join(loaded))
        """
    )
    assert result.returncode == 0, result.stderr
    loaded = result.stdout.split()
    packages = sorted({".".join(m.split(".")[:2]) for m in loaded})
    assert not loaded, f"loading the {name} filter imports {packages}"


ZOPE_CONF = """\
%define INSTANCE {instance}
instancehome $INSTANCE
clienthome $INSTANCE/var
<environment>
    CHAMELEON_CACHE {cache}
</environment>
<zodb_db main>
    <mappingstorage>
    </mappingstorage>
    mount-point /
</zodb_db>
"""

ZOPE_INI = """\
[app:zope]
use = egg:Zope#main
zope_conf = %(here)s/zope.conf

[filter:healthserver]
use = egg:plone.observability#healthserver

[filter:observability]
use = egg:plone.observability#observability

[filter:opentelemetry]
use = egg:plone.observability#opentelemetry

[pipeline:main]
pipeline =
    egg:Zope#httpexceptions
    healthserver
    observability
    opentelemetry
    zope
"""


def test_zope_conf_reaches_modules_with_all_filters(tmp_path):
    cache = tmp_path / "var" / "cache"
    cache.mkdir(parents=True)
    (tmp_path / "zope.conf").write_text(
        ZOPE_CONF.format(instance=tmp_path, cache=cache)
    )
    (tmp_path / "zope.ini").write_text(ZOPE_INI)
    result = run(
        f"""
        from paste.deploy import loadapp

        loadapp("config:{tmp_path / "zope.ini"}")

        import chameleon.config
        import OFS.ObjectManager

        print(chameleon.config.CACHE_DIRECTORY)
        print(OFS.ObjectManager.CONFIG.instancehome)
        """,
        env={
            "PATH": "",
            "PLONE_OBSERVABILITY_HEALTH_PORT": "0",
            "PLONE_OBSERVABILITY_OTEL_ENABLED": "0",
        },
    )
    assert result.returncode == 0, result.stderr
    cache_directory, instancehome = result.stdout.split()
    assert cache_directory == str(cache)
    assert instancehome == str(tmp_path)
