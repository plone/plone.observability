from dataclasses import dataclass
from dataclasses import field


@dataclass
class Metric:
    """A single metric data point."""

    name: str
    value: float
    type: str  # "gauge", "counter", "histogram", "info"
    scope: str  # "global" or "instance"
    help: str
    labels: dict = field(default_factory=dict)
