from zope.interface import Attribute
from zope.interface import Interface


class ILivenessCheck(Interface):
    """Named utility for liveness checks.

    Implementations MUST NOT access ZODB or any blocking resource.
    These run on the health server thread, outside of Zope context.
    """

    name = Attribute("Human-readable name of the check")

    def __call__():
        """Run the liveness check.

        Returns a tuple of (ok: bool, message: str).
        """


class IReadinessCheck(Interface):
    """Named utility for readiness checks.

    May access ZODB and other resources. These checks verify the
    application can serve real requests.
    """

    name = Attribute("Human-readable name of the check")

    def __call__():
        """Run the readiness check.

        Returns a tuple of (ok: bool, message: str).
        """


class IMetricProvider(Interface):
    """Adapter on the application root providing metrics.

    The scope attribute indicates whether metrics are global (same across
    all instances sharing a ZODB) or instance-specific.
    """

    name = Attribute("Provider name")
    scope = Attribute("'global' (shared across instances) or 'instance'")

    def collect():
        """Collect current metrics.

        Yields Metric instances.
        """


class IMetricFormatter(Interface):
    """Named utility that serializes metrics to a specific wire format."""

    content_type = Attribute("MIME type for the response")

    def format(metrics):
        """Format a sequence of Metric objects.

        Returns a string in the target format.
        """
