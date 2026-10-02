"""Upstream forwarding (PX-004…PX-009, UP-008, UP-009).

Requests are sent with exactly the headers given (no client defaults such as ``user-agent`` or
``accept-encoding`` are added). Responses are streamed and relayed as raw bytes, so content
encodings pass through untouched. The read timeout applies between chunks (UP-009).
"""

from __future__ import annotations

import ssl
from collections.abc import Sequence

import certifi
import httpx

from tokli.domain.headers import hop_by_hop


class UpstreamError(Exception):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind  # "upstream_unreachable" | "upstream_timeout"


def ssl_context(ca_bundle: str | None) -> ssl.SSLContext:
    """Verification is always on; a custom CA bundle is used only when configured (UP-008)."""
    return ssl.create_default_context(cafile=ca_bundle or certifi.where())


class Upstream:
    def __init__(
        self,
        base_url: str,
        connect_timeout_s: float,
        read_timeout_s: float,
        ca_bundle: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=connect_timeout_s,
            read=read_timeout_s,
            write=read_timeout_s,
            pool=connect_timeout_s,
        )
        self._ca_bundle = ca_bundle
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                verify=ssl_context(self._ca_bundle),
                follow_redirects=False,
                trust_env=False,
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def open(
        self,
        method: str,
        path: str,
        query: str,
        headers: Sequence[tuple[str, str]],
        body: bytes,
    ) -> httpx.Response:
        """Sends the request and returns the streaming response (not yet read)."""
        if self._client is None:
            await self.start()
        assert self._client is not None
        url = self._base_url + path + (f"?{query}" if query else "")
        request = self._client.build_request(method, url, content=body)
        given = {name.lower() for name, _ in headers}
        for default in ("accept", "accept-encoding", "user-agent", "connection"):
            if default not in given and default in request.headers:
                del request.headers[default]
        for name, value in headers:
            request.headers[name] = value
        try:
            return await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise UpstreamError("upstream_timeout", type(exc).__name__) from exc
        except httpx.TransportError as exc:
            raise UpstreamError("upstream_unreachable", type(exc).__name__) from exc


def response_headers(response: httpx.Response, *, streaming: bool) -> list[tuple[str, str]]:
    """Upstream headers to relay: all except hop-by-hop, and ``content-length`` when streaming."""
    items = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in response.headers.raw]
    drop = hop_by_hop(items)
    if streaming:
        drop = drop | {"content-length"}
    return [(name, value) for name, value in items if name.lower() not in drop]
