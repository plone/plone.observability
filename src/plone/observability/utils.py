"""Small helpers without Zope or Plone imports.

The WSGI filter modules import these while PasteDeploy builds the pipeline, before
zope.conf is applied (#105), so nothing here may import Zope or Plone.
"""

_TRUTHY = frozenset({"1", "y", "yes", "t", "true", "active", "enabled", "on"})
_FALSY = frozenset({"0", "n", "no", "f", "false", "inactive", "disabled", "off"})


def boolean_value(value, default=None):
    """Return a boolean for *value*, like ``plone.base.utils.boolean_value``.

    Recognizes booleans, the integers 1 and 0, and the usual yes/no strings. An
    unrecognized value returns *default* when it is a boolean, else raises
    ValueError.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
    else:
        text = str(value).lower().strip()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
    if isinstance(default, bool):
        return default
    raise ValueError(f"Could not parse value {value!r} as boolean")
