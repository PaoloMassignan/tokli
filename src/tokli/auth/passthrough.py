"""Passthrough auth (UP-002, UP-006, UP-010) and request-header forwarding rules (PX-004).

In passthrough mode the client's credential headers travel unchanged; Tokli never stores them.
``credential_kind`` looks only at header names and well-known prefixes, never keeps values.
"""

from __future__ import annotations

from collections.abc import Iterable

from tokli.domain.headers import HOP_BY_HOP, hop_by_hop

__all__ = ["HOP_BY_HOP", "credential_kind", "forward_request_headers", "header_names", "hop_by_hop"]

Headers = list[tuple[str, str]]
_NOT_FORWARDED = frozenset({"host", "content-length"})


def forward_request_headers(headers: Iterable[tuple[str, str]]) -> Headers:
    """Client headers to send upstream: all except hop-by-hop, ``host`` and ``content-length``."""
    items = list(headers)
    drop = hop_by_hop(items) | _NOT_FORWARDED
    return [(name, value) for name, value in items if name.lower() not in drop]


def credential_kind(headers: Iterable[tuple[str, str]]) -> str:
    """``api_key``, ``oauth``, ``none`` or ``unknown``, from header names and prefixes only."""
    kind = "none"
    for name, value in headers:
        lowered = name.lower()
        if lowered == "x-api-key":
            return "api_key"
        if lowered == "authorization":
            token = value.split(" ", 1)[1].strip() if " " in value else value.strip()
            if token.startswith("sk-ant-oat"):
                kind = "oauth"
            elif token.startswith(("sk-ant-api", "sk-")):
                kind = "api_key"
            else:
                kind = "unknown"
    return kind


def header_names(headers: Iterable[tuple[str, str]]) -> list[str]:
    """Lower-cased, sorted, de-duplicated header names; never values (OB-012)."""
    return sorted({name.lower() for name, _ in headers})
