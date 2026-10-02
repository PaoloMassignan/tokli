"""HTTP header semantics shared by request forwarding and response relay (RFC 9110 §7.6.1)."""

from __future__ import annotations

from collections.abc import Iterable

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-connection",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def hop_by_hop(headers: Iterable[tuple[str, str]]) -> frozenset[str]:
    """Hop-by-hop names, including every header named in ``connection``."""
    listed: set[str] = set()
    for name, value in headers:
        if name.lower() == "connection":
            listed.update(token.strip().lower() for token in value.split(",") if token.strip())
    return HOP_BY_HOP | listed
