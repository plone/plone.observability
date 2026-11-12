from plone.base.utils import boolean_value as plone_boolean_value
from plone.observability.utils import boolean_value

import pytest


VALUES = [
    True,
    False,
    1,
    0,
    2,
    -1,
    1.0,
    None,
    "",
    "1",
    "0",
    "y",
    "n",
    "yes",
    "no",
    "t",
    "f",
    "true",
    "false",
    "on",
    "off",
    "active",
    "inactive",
    "enabled",
    "disabled",
    " Yes ",
    "TRUE",
    "Off",
    "maybe",
    "2",
]


@pytest.mark.parametrize("value", VALUES, ids=repr)
@pytest.mark.parametrize("default", [None, True, False])
def test_same_as_plone_base(value, default):
    """The local helper replaces plone.base's to keep plone.base out of the
    filter modules' imports (#105); it must behave the same."""
    try:
        expected = plone_boolean_value(value, default=default)
    except ValueError:
        with pytest.raises(ValueError):
            boolean_value(value, default=default)
    else:
        assert boolean_value(value, default=default) is expected
