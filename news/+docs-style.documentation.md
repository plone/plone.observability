Bring the documentation to the Plone documentation style and correct facts that
had drifted from the code. Most important: tracing requires the `opentelemetry`
WSGI filter, which sets up the exporter and installs the instrumentation; the docs
claimed some spans worked without it. The tracing explanation now says which spans
come from events and which from wrappers, the span reference lists the render
spans, and `llms.txt` is rewritten. Page metadata now reaches the HTML, and the
documentation build runs with `-W` and a prose check on pull requests.
