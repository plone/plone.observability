# About health probes

A container orchestrator needs to know three different things about a Plone process, and they are genuinely different questions.
This page explains why plone.observability answers them with three separate probes on a port of their own, rather than reusing Plone's `@@ok` view.

## The problem with `@@ok`

Plone has long shipped an `@@ok` view, and it is tempting to point a health check at it.
The trouble is that `@@ok` returns `OK` whether the ZODB is reachable or not.
It keeps returning `OK` right up until the process is so busy that it cannot answer at all.

That is the worst possible failure shape for an orchestrator.
A health signal that is green when the database is gone gives you false confidence, and a health signal that only turns red once the process is already saturated tells you nothing you can act on in time.
An orchestrator needs signals that distinguish *alive* from *ready* from *finished starting*, and it needs them to stay truthful under load.

## Why three probes, not one

Kubernetes models a container's health with three probes because the right reaction to each failure is different.

Liveness asks whether the process is fundamentally functional.
A failed liveness check triggers a restart, so it must not depend on anything outside the process.
A database check does not belong here: a brief ZODB outage would fail liveness across every pod at once, and the orchestrator would respond by restarting them all, turning a transient dependency blip into a restart storm.

Readiness asks whether the process can serve traffic right now.
This is where ZODB connectivity belongs.
When the database is unreachable, a pod should be pulled out of the load balancer rotation, not killed; once the database returns, the same pod can start serving again without a restart.

Startup asks whether initialization has finished.
Plone boots slowly, and without a dedicated startup signal the liveness probe would start checking too early and restart a process that was simply still booting.
The startup probe holds the liveness probe off until Plone is actually up.

## Why `/startup` latches

The startup probe in plone.observability evaluates the readiness checks itself and latches on the first success.
Once it turns green, it stays green.

This is not laziness; it is forced by the order Kubernetes runs probes in.
Kubernetes does not run the readiness probe at all until the startup probe has succeeded.
Implementing `/startup` as "has `/ready` passed at least once" cannot work: at startup time, `/ready` has never been polled, and never will be until `/startup` is already green.
The two would deadlock.
Evaluating the readiness checks directly and latching on first success breaks the chicken-and-egg and lets `/startup` stand on its own.

## Why a separate port and thread

The health server runs in a background daemon thread on its own port, the default being `8081`, completely separate from the Zope WSGI server.

The reason is the exact failure the probes exist to detect.
When every Zope worker thread is busy serving slow requests, a health endpoint that runs through the same WSGI stack would queue behind them and time out.
The orchestrator would read that timeout as "process dead" and restart a process that was merely under load, throwing away in-flight work and making the overload worse.
A dedicated thread on a dedicated port stays answerable through saturation, so the liveness signal reports what is actually true: the process is alive, just busy.

## Why metrics are different

Metrics deliberately do the opposite.
They run on the standard Zope port, alongside the application, and they need a working database connection to produce meaningful numbers.

This contrast is intentional and worth holding onto.
A health check must survive the loss of its dependencies in order to report that loss accurately.
A metrics endpoint needs those dependencies present in order to measure them.
They have opposite requirements, so they live in opposite places.

```{seealso}
- {doc}`/reference/health-endpoints` for the exact endpoints and response format.
- {doc}`/how-to/configure-kubernetes-probes` to wire these probes into a deployment.
- The introduction on the Plone community forum: <https://community.plone.org/t/plone-observability-health-probes-and-metrics-for-running-plone-in-containers>
```
