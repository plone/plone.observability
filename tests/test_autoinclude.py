def test_declares_autoinclude_plugin_target_plone():
    from importlib.metadata import entry_points

    eps = entry_points().select(group="z3c.autoinclude.plugin")
    mine = [e for e in eps if e.dist and e.dist.name == "plone.observability"]
    assert any(e.name == "target" and e.value == "plone" for e in mine), (
        f"missing z3c.autoinclude.plugin target=plone; got {[(e.name, e.value) for e in mine]}"
    )
