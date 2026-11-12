# Get plone.observability running

In this tutorial we will start a Plone backend with plone.observability wired in.
We will watch its three health probes turn green and read live metrics from the running process.
Everything runs in Docker.
You need nothing else installed.

## Before you start

You need Docker with the Compose plugin.
Check that it works:

```console
$ docker compose version
Docker Compose version v2.30.3
```

Any recent version is fine.

## Step 1: Create the project file

Make a new directory and, inside it, create a file named `docker-compose.yml` with this content:

```yaml
services:
  plone:
    image: plone/plone-backend:6.2
    environment:
      ADDONS: "plone.observability"
    ports:
      - "8080:8080"
      - "8081:8081"
    configs:
      - source: zope_ini
        target: /app/etc/zope.ini

configs:
  zope_ini:
    content: |
      [app:zope]
      use = egg:Zope#main
      zope_conf = %(here)s/%(config_file)s

      [server:main]
      use = egg:waitress#main
      host = 0.0.0.0
      port = 8080
      threads = 2

      [filter:translogger]
      use = egg:Paste#translogger
      setup_console_handler = False

      [filter:healthserver]
      use = egg:plone.observability#healthserver

      [filter:observability]
      use = egg:plone.observability#observability

      [pipeline:main]
      pipeline =
          egg:Zope#httpexceptions
          healthserver
          observability
          translogger
          zope

      [loggers]
      keys = root

      [handlers]
      keys = eventlog

      [formatters]
      keys = generic

      [formatter_generic]
      format = %(asctime)s %(levelname)s [%(name)s] %(message)s

      [logger_root]
      level = INFO
      handlers = eventlog

      [handler_eventlog]
      class = StreamHandler
      args = (sys.stderr,)
      level = INFO
      formatter = generic
```

You do not need to understand every line yet.
The important part is the `[pipeline:main]` section, where the `healthserver` and `observability` filters sit in front of Zope.
Those two lines are what turn an ordinary Plone into an observable one.

## Step 2: Start Plone

From the same directory, run:

```shell
docker compose up
```

The first run downloads the Plone image and installs plone.observability.
It takes a minute or two.
Watch the log.
Plone is ready when you see this line:

```text
INFO [waitress] Serving on http://0.0.0.0:8080
```

Notice the line just before it, `Health server started on 0.0.0.0:8081`.
plone.observability is wired in.

Leave this terminal running and open a second one for the next steps.

## Step 3: Watch the liveness probe

The health server listens on port `8081`, separate from Plone's own port `8080`.
Ask it whether the process is alive:

```console
$ curl http://localhost:8081/live
{"status": "ok", "checks": {}}
```

A `200` response with `"status": "ok"` means the process is alive.
Notice that `checks` is empty.
Liveness does not touch the database.

## Step 4: Watch the readiness probe

Now ask whether Plone can actually serve requests:

```console
$ curl http://localhost:8081/ready
{"status": "ok", "checks": {"zodb": {"ok": true, "message": "ZODB connection ok"}}}
```

This time the response carries a `zodb` check.
Readiness confirms that the database connection works.

## Step 5: Watch the startup probe

```console
$ curl http://localhost:8081/startup
{"status": "ok"}
```

The startup probe reports that initialization has finished.
Once it has turned green, it stays green.

All three probes answer.
Kubernetes reads these same signals to decide when to restart Plone, when to send it traffic, and when its boot is over.

## Step 6: Read the metrics

Metrics live on Plone's own port, `8080`, at the `@@metrics` view:

```console
$ curl http://localhost:8080/@@metrics
# HELP plone_uptime_seconds Process uptime in seconds
# TYPE plone_uptime_seconds gauge
plone_uptime_seconds{scope="instance"} 15.37
# HELP plone_info Version information
# TYPE plone_info gauge
plone_info{scope="instance",python_version="3.13.13",zope_version="6.1",plone_version="6.2.0"} 1
```

This is Prometheus text format, the same format a Prometheus server scrapes.
You can recognize the Plone, Zope, and Python versions of your running process right there in `plone_info`.

## Step 7: Make a metric move

Find the request counter:

```console
$ curl --silent http://localhost:8080/@@metrics | grep plone_requests_total
# HELP plone_requests_total Total number of HTTP requests
# TYPE plone_requests_total counter
plone_requests_total{scope="instance",auth="authenticated"} 0
plone_requests_total{scope="instance",auth="anonymous"} 2
```

Run that same command a few more times and watch the number climb.
Each scrape is itself an anonymous request.
The `auth="anonymous"` counter goes up every time you ask.

## Step 8: Clean up

Back in the first terminal, stop Plone with {kbd}`Ctrl+C`, then remove the container and its data:

```shell
docker compose down -v
```

You have watched a real Plone report its own health and measure its own traffic.

```{seealso}
- {doc}`/how-to/configure-kubernetes-probes` to run this in Kubernetes.
- {doc}`/how-to/scrape-with-prometheus` to collect these metrics with a Prometheus server.
- {doc}`/explanation/health-probes` for why the probes are split the way they are.
```
