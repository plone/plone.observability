# About health probes

A container orchestrator needs to know three different things about a Plone process, and they are genuinely different questions.
This page explains why plone.observability answers them with three separate probes on a port of their own, rather than reusing Plone's `@@ok` view.

## The problem with `@@ok`

Plone has long shipped an `@@ok` view, and it is tempting to point a health check at it.
The trouble is that `@@ok` returns `OK` whether the ZODB is reachable or not.
It keeps returning `OK` right up until the process is so busy that it cannot answer at all.

That is the worst possible failure shape for an orchestrator.
A health signal that is green when the database is gone gives you false confidence.
A health signal that only turns red once the process is already saturated tells you nothing you can act on in time.
An orchestrator needs signals that distinguish *alive* from *ready* from *finished starting*, and it needs them to stay truthful under load.

## Why three probes, not one

Kubernetes models a container's health with three probes because the right reaction to each failure is different.

Liveness asks whether the process is fundamentally functional.
A failed liveness check triggers a restart.
It must not depend on anything outside the process.
A database check does not belong here.
A brief ZODB outage would fail liveness across every pod at once.
The orchestrator would respond by restarting them all, turning a transient dependency blip into a restart storm.

Readiness asks whether the process can serve traffic right now.
This is where ZODB connectivity belongs.
When the database is unreachable, the load balancer should pull a pod out of its rotation.
Restarting the pod would not bring the database back.
Once the database returns, the same pod can start serving again without a restart.

Startup asks whether initialization has finished.
Plone boots slowly.
Without a dedicated startup signal, the liveness probe would start checking too early.
It would then restart a process that was still booting.
The startup probe holds the liveness probe off until Plone is actually up.

## Why `/startup` latches

The startup probe in plone.observability evaluates the readiness checks itself and latches on the first success.
Once it turns green, it stays green.

The order in which Kubernetes runs probes forces this behavior.
Kubernetes does not run the readiness probe at all until the startup probe has succeeded.
Implementing `/startup` as "has `/ready` passed at least once" cannot work: at startup time, `/ready` has never been polled, and never will be until `/startup` is already green.
The two would deadlock.
Evaluating the readiness checks directly and latching on first success breaks the chicken-and-egg and lets `/startup` stand on its own.

## Why a separate port and thread

The health server runs in a background daemon thread on its own port, the default being `8081`, completely separate from the Zope WSGI server.

The reason is the exact failure the probes exist to detect.
Suppose every Zope worker thread is busy serving slow requests.
A health endpoint that runs through the same WSGI stack would queue behind them and time out.
The orchestrator would read that timeout as "process dead".
It would restart a process that was merely under load, throwing away in-flight work and making the overload worse.
A dedicated thread on a dedicated port stays answerable through saturation.
The liveness signal then reports what is actually true: the process is alive, just busy.

## Why readiness runs one check at a time

The health server answers each probe on its own thread.
A busy Zope cannot delay it.
That alone is not enough: the readiness check opens a ZODB connection, and opening one can block, for example while the database fails over.
The kubelet gives up on a probe after its timeout and sends the next one.
If every probe started its own check, each would add another thread waiting for the same database.
The waiting threads would compete with the Zope workers for the same locks.
A short outage could then turn into a process that never recovers.

So readiness is single-flight.
Only one run of the readiness checks happens at a time, in the probe thread that started it.
Every other probe answers at once: with the last result while the run is young, and with "not ready" once it has been running too long.
A blocked check holds exactly one thread, and the probes keep telling the truth: this process cannot serve right now.
A short result cache lets a burst of probes share a single check.

## Why readiness borrows a pool connection

The ZODB check opens a connection with `db.open()`, reads the root object, and closes it again.
That is the same path every request takes, including the lock the database holds while it hands out connections.
A check that only asked the storage would be cheaper.
It would stay green while requests pile up on that lock.
That is exactly the situation a readiness probe has to catch.

The price shows up in the log when the instance is busy.
If every worker thread holds a connection when the probe runs, `db.open()` creates one beyond `pool-size`, and ZODB warns:

```text
WARNING [ZODB.DB:158] DB.open() has 4 open connections with a pool_size of 3
```

The warning is harmless.
ZODB keeps idle connections sorted by the size of their object cache and discards the smallest one when the pool is over its size.
That is the probe's connection, which holds next to nothing.
The warm caches of the worker threads survive.
The warning does tell you that all worker connections were busy at that moment.
The metric `plone_zodb_connections_idle` shows the same saturation over time.

To silence it, set `pool-size` one higher than the number of worker threads.
The probe then has a slot of its own.
That extra connection can warm up over time when the workers use it.
Budget memory for one more object cache.

## Why metrics are different

Metrics deliberately do the opposite.
They run on the standard Zope port, alongside the application, and they need a working database connection to produce meaningful numbers.

This contrast is intentional and worth holding onto.
A health check must survive the loss of its dependencies to report that loss accurately.
A metrics endpoint needs those dependencies present to measure them.
The two have opposite requirements and live in opposite places.

```{seealso}
- {doc}`/reference/health-endpoints` for the exact endpoints and response format.
- {doc}`/how-to/configure-kubernetes-probes` to wire these probes into a deployment.
- The introduction on the Plone community forum: <https://community.plone.org/t/plone-observability-health-probes-and-metrics-for-running-plone-in-containers/23081>
```
