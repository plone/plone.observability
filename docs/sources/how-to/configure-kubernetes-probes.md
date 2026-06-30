# How to configure Kubernetes health probes

This guide shows you how to point Kubernetes liveness, readiness, and startup probes at the plone.observability health server.

It assumes the `healthserver` filter is wired and the health server listens on port `8081`.
See {doc}`/how-to/install`.

## Expose the health port

Declare the health port on the container alongside the main Zope port.

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: health
    containerPort: 8081
```

## Configure the three probes

```yaml
livenessProbe:
  httpGet:
    path: /live
    port: 8081
  initialDelaySeconds: 10
  periodSeconds: 30
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8081
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /startup
    port: 8081
  failureThreshold: 30
  periodSeconds: 10
```

## Tune the startup budget for slow boots

Plone can take a while to boot.
The startup probe protects it: Kubernetes runs the liveness and readiness probes only after the startup probe has succeeded.

Size the startup budget to your slowest realistic boot.
With `failureThreshold: 30` and `periodSeconds: 10`, Kubernetes allows up to 300 seconds for startup before it gives up.
Raise `failureThreshold` if your site boots more slowly; the probe latches green on first success, so a generous budget costs nothing on a fast boot.

```{seealso}
- {doc}`/reference/health-endpoints` for the endpoint semantics and the `/startup` latch.
- {doc}`/explanation/health-probes` for why the three probes are separate and why the budget matters.
```
