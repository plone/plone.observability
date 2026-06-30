# Get plone.observability running

In this tutorial we will start a Plone backend with plone.observability wired in, watch its three health probes turn green, and read live metrics from the running process.
Everything runs in Docker, so you do not install anything except Docker itself.

By the end you will have seen, with your own eyes, the signals that an orchestrator like Kubernetes uses to manage Plone.

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

The first run downloads the Plone image and installs plone.observability, so it takes a minute or two.
Watch the log.
When you see a line like `Using default configuration` followed by the Zope startup messages, Plone is ready.

Leave this terminal running and open a second one for the next steps.

## Step 3: Watch the liveness probe

The health server listens on port `8081`, separate from Plone's own port `8080`.
Ask it whether the process is alive:

```console
$ curl http://localhost:8081/live
{"status": "ok", "checks": {}}
```

A `200` response with `"status": "ok"` means the process is alive.
Notice that `checks` is empty: liveness deliberately does not touch the database, so it stays answerable even when the database is down.

## Step 4: Watch the readiness probe

Now ask whether Plone can actually serve requests:

```console
$ curl http://localhost:8081/ready
{"status": "ok", "checks": {"zodb": {"ok": true, "message": "ZODB connection ok"}}}
```

This time the response carries a `zodb` check.
Readiness confirms that the database connection works, because a process that cannot reach its database should be pulled out of rotation, not restarted.

## Step 5: Watch the startup probe

```console
$ curl http://localhost:8081/startup
{"status": "ok"}
```

The startup probe reports that initialization has finished.
Once it has turned green it stays green, which is exactly what Kubernetes needs to know that the slow boot is over.

All three probes answer.
You are looking at the same signals Kubernetes reads to decide when to restart Plone, when to send it traffic, and when to stop waiting for it to boot.

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
plone_requests_total{scope="instance",auth="anonymous"} 2
```

Run that same command a few more times and watch the number climb.
Each scrape is itself an anonymous request, so the `auth="anonymous"` counter goes up every time you ask.
You have just watched Plone measure its own traffic.

## Step 8: Clean up

Back in the first terminal, stop Plone with {kbd}`Ctrl+C`, then remove the container and its data:

```shell
docker compose down -v
```

## What you have done

You started a real Plone backend with plone.observability wired into its WSGI pipeline.
You saw the liveness, readiness, and startup probes answer on a dedicated port, and you read live Prometheus metrics from the running process, including a counter that moved as you watched.

From here:

- To run this for real in Kubernetes, follow {doc}`/how-to/configure-kubernetes-probes`.
- To collect these metrics with a Prometheus server, follow {doc}`/how-to/scrape-with-prometheus`.
- To understand why the probes are split the way they are, read {doc}`/explanation/health-probes`.
