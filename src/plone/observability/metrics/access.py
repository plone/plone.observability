import os
from ipaddress import ip_address
from ipaddress import ip_network


def _get_cidrs(env_var, default=""):
    raw = os.environ.get(env_var, default).strip()
    if not raw:
        return []
    return [ip_network(c.strip(), strict=False) for c in raw.split(",") if c.strip()]


def _get_client_ip(peer_ip, headers):
    """Determine the real client IP, respecting trusted proxies."""
    trusted = _get_cidrs(
        "PLONE_OBSERVABILITY_TRUSTED_PROXIES", default="127.0.0.1,::1"
    )
    try:
        peer = ip_address(peer_ip)
    except ValueError:
        return peer_ip

    if not any(peer in net for net in trusted):
        return peer_ip

    forwarded = headers.get("X-Forwarded-For", "")
    if not forwarded:
        return peer_ip

    # Walk the chain from right to left, skipping trusted proxies.
    # The first non-trusted IP is the real client.
    parts = [p.strip() for p in forwarded.split(",")]
    for part in reversed(parts):
        try:
            addr = ip_address(part)
        except ValueError:
            continue
        if not any(addr in net for net in trusted):
            return part
    return peer_ip


def is_allowed(peer_ip, headers):
    """Check if a request is allowed based on IP allow-list."""
    allowlist = _get_cidrs("PLONE_OBSERVABILITY_METRICS_ALLOWLIST")
    if not allowlist:
        return True

    client_ip_str = _get_client_ip(peer_ip, headers)
    try:
        client_ip = ip_address(client_ip_str)
    except ValueError:
        return False

    return any(client_ip in net for net in allowlist)
