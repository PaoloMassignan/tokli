"""``tokli serve``: listener preparation (PX-001, PT-008)."""

from __future__ import annotations

import ipaddress
import os
import socket

from tokli.config import EffectiveConfig


class ListenError(Exception):
    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.fix = fix


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def prepare_listener(config: EffectiveConfig) -> socket.socket:
    """Binds the configured address. Refuses a non-loopback host unless allowed (PX-001) and
    reports a port in use as a one-line cause and fix (PT-008). Never auto-increments the port."""
    server = config.settings.server
    host, port = server.host, server.port
    if not is_loopback(host) and not server.allow_remote:
        raise ListenError(
            cause=f"refusing to listen on {host}: it is not a loopback address",
            fix="pass --allow-remote (or set server.allow_remote) to expose Tokli on the network",
        )
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            # Windows-only option: no other process may bind the same port (PT-008).
            sock.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE"), 1)  # noqa: B009
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
    except OSError as exc:
        sock.close()
        in_use = getattr(exc, "winerror", None) == 10048 or exc.errno in (48, 98, 10048)
        if in_use:
            raise ListenError(
                cause=f"port {port} on {host} is already in use",
                fix="stop the other process or choose another port with --port",
            ) from exc
        raise ListenError(
            cause=f"cannot listen on {host}:{port}: {exc.strerror or exc}",
            fix="choose another address with --set server.host=… or another port with --port",
        ) from exc
    return sock
