# Health endpoints

The health server runs on a dedicated port (default `8081`) in a background daemon thread, separate from the Zope WSGI server.
It answers even when all Zope worker threads are busy.

The health server is started by the `egg:plone.observability#healthserver` WSGI filter.
It is not started on Zope process startup, so `zconsole` and script runs never touch the health port.
See {doc}`/how-to/install` for wiring the filter.

## Endpoints

`/live`
:   Liveness check.
    Answers whether the process is alive.
    Must not depend on the database or any external service.

`/ready`
:   Readiness check.
    Answers whether the process can currently serve requests.
    Evaluates the registered readiness checks, including ZODB connectivity.

`/startup`
:   Startup check.
    Answers whether the process has finished initializing.
    Evaluates the readiness checks itself and latches on the first success: once it turns green, it stays green.

The `/startup` latch is deliberate.
Kubernetes does not run the readiness probe until the startup probe has succeeded, so `/startup` cannot depend on `/ready` having been polled first.
It must stand on its own.

## Response format

All endpoints return JSON.
The HTTP status is `200` on success and `503` on failure.

```json
{
  "status": "ok",
  "checks": {
    "zodb": {"ok": true, "message": "ZODB connection ok"}
  }
}
```

Each entry in `checks` is keyed by the check name and reports a boolean `ok` and a human-readable `message`.

```{seealso}
{doc}`/explanation/health-probes` explains why there are three separate probes and why the server runs on its own port.
{doc}`/how-to/configure-kubernetes-probes` shows how to point Kubernetes at these endpoints.
```
