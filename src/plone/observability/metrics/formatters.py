from plone.observability.interfaces import IMetricFormatter
from zope.interface import implementer

import json


@implementer(IMetricFormatter)
class PrometheusFormatter:
    """Formats metrics in Prometheus text exposition format."""

    content_type = "text/plain; version=0.0.4; charset=utf-8"

    def format(self, metrics):
        lines = []
        seen = set()
        for m in metrics:
            if m.name not in seen:
                lines.append(f"# HELP {m.name} {m.help}")
                lines.append(f"# TYPE {m.name} {m.type}")
                seen.add(m.name)
            labels = {"scope": m.scope}
            labels.update(m.labels)
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            value = int(m.value) if m.value == int(m.value) else m.value
            lines.append(f"{m.name}{{{label_str}}} {value}")
        return "\n".join(lines) + "\n"


@implementer(IMetricFormatter)
class JSONFormatter:
    """Formats metrics as JSON."""

    content_type = "application/json"

    def format(self, metrics):
        data = []
        for m in metrics:
            entry = {
                "name": m.name,
                "value": m.value,
                "type": m.type,
                "scope": m.scope,
                "help": m.help,
            }
            if m.labels:
                entry["labels"] = m.labels
            data.append(entry)
        return json.dumps(data)
