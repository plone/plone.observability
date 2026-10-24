# How to add a custom health check

This guide shows you how to add your own liveness or readiness check.
Use a liveness check for something that proves the process itself is alive, and a readiness check for a dependency the process needs in order to serve traffic.

For the interface members, see {doc}`/reference/interfaces`.

## Add a liveness check

A liveness check must not access ZODB and must not block.
Implement `ILivenessCheck` and register it as a named utility.

```python
from zope.interface import implementer
from plone.observability.interfaces import ILivenessCheck


@implementer(ILivenessCheck)
class MyLivenessCheck:
    name = "myapp"

    def __call__(self):
        return True, "all good"
```

```xml
<utility
    factory=".checks.MyLivenessCheck"
    provides="plone.observability.interfaces.ILivenessCheck"
    name="myapp"
    />
```

## Add a readiness check

A readiness check may access ZODB and any dependency the process needs to serve requests.
Implement `IReadinessCheck`.

```python
from zope.interface import implementer
from plone.observability.interfaces import IReadinessCheck


@implementer(IReadinessCheck)
class MyReadinessCheck:
    name = "myapp"

    def __call__(self):
        ok = _check_external_service()
        return ok, "service ok" if ok else "service unavailable"
```

```xml
<utility
    factory=".checks.MyReadinessCheck"
    provides="plone.observability.interfaces.IReadinessCheck"
    name="myapp"
    />
```

The check name appears under `checks` in the probe response, keyed by the `name` attribute.

Readiness checks run together, one run at a time, and the result is reused for a short time.
A check does not need its own locking or caching against concurrent probes.
It should still return within a few seconds: while a run is stuck, the pod reports not ready.
See {doc}`/explanation/health-probes`.

```{seealso}
{doc}`/explanation/health-probes` explains the difference between liveness and readiness and why the distinction matters.
```
