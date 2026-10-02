"""Real servers for integration tests: a scripted fake upstream and Tokli itself, each served by
uvicorn on an ephemeral loopback port in a background thread (TOKLI_TEST_STRATEGY §2)."""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import socket
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from tests.helpers import home_env, platform_name
from tokli.app.bootstrap import Services, bootstrap
from tokli.config import CliOverrides, EffectiveConfig, load_config
from tokli.http.app import create_app
from tokli.observability.logs import configure_logging
from tokli.tokens import CATALOG, TokenizerSpec, tokenizer_dir


def byte_level_bpe() -> bytes:
    """A valid tokenizer file whose tokens are single bytes (count = UTF-8 bytes per piece)."""
    return b"".join(
        base64.b64encode(bytes([b])) + b" " + str(b).encode() + b"\n" for b in range(256)
    )


BPE = byte_level_bpe()
BYTE_CATALOG = {
    "o200k_base": TokenizerSpec(
        name="o200k_base",
        filename="o200k_base.tiktoken",
        url="https://tokenizers.invalid/o200k_base.tiktoken",
        sha256=hashlib.sha256(BPE).hexdigest(),
        pattern=CATALOG["o200k_base"].pattern,
        special_tokens={},
    )
}


@dataclass
class Received:
    method: str
    path: str
    query: str
    headers: list[tuple[str, str]]
    body: bytes


Responder = Callable[[Request], Awaitable[Response]]


async def default_responder(request: Request) -> Response:
    return JSONResponse({"id": "msg_test", "type": "message", "content": []})


@dataclass
class FakeUpstream:
    received: list[Received] = field(default_factory=list)
    responder: Responder = default_responder
    url: str = ""

    def app(self) -> Starlette:
        async def handle(request: Request) -> Response:
            body = await request.body()
            self.received.append(
                Received(
                    request.method,
                    request.url.path,
                    request.url.query,
                    [(k.decode("latin-1"), v.decode("latin-1")) for k, v in request.headers.raw],
                    body,
                )
            )
            return await self.responder(request)

        return Starlette(
            routes=[
                Route("/{path:path}", handle, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
            ]
        )


def free_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


@contextmanager
def serve(app: Any, sock: socket.socket | None = None) -> Iterator[str]:
    sock = sock or free_socket()
    port = sock.getsockname()[1]
    config = uvicorn.Config(
        app, log_config=None, access_log=False, lifespan="on", log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("server did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def provision(data_dir: Path) -> None:
    target = tokenizer_dir(data_dir) / BYTE_CATALOG["o200k_base"].filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(BPE)


def make_config(
    tmp_path: Path, upstream_url: str, *sets: str, env: dict[str, str] | None = None
) -> EffectiveConfig:
    data_dir = tmp_path / "data"
    provision(data_dir)
    base = [f"upstreams.anthropic.base_url={upstream_url}"]
    return load_config(
        CliOverrides(data_dir=str(data_dir), config_dir=str(tmp_path / "cfg"), sets=(*base, *sets)),
        {**home_env(tmp_path / "home"), **(env or {})},
        platform_name(),
    )


@dataclass
class Tokli:
    url: str
    services: Services
    logs: io.StringIO

    def wait_trace(self, request_id: str, timeout_s: float = 5.0) -> dict[str, Any]:
        """The request's API view. Tokli records a request just after relaying its last byte,
        so a client can finish before the record exists: poll until it does."""
        import httpx

        deadline = time.monotonic() + timeout_s
        while True:
            response = httpx.get(f"{self.url}/tokli/api/requests/{request_id}", timeout=5)
            if response.status_code == 200 or time.monotonic() > deadline:
                assert response.status_code == 200, f"no trace for {request_id}"
                result: dict[str, Any] = response.json()
                return result
            time.sleep(0.02)

    def log_lines(self) -> list[str]:
        return [line for line in self.logs.getvalue().splitlines() if line.strip()]


@contextmanager
def run_tokli(config: EffectiveConfig, services: Services | None = None) -> Iterator[Tokli]:
    services = services or bootstrap(config, catalog=BYTE_CATALOG, version="test")
    logs = io.StringIO()
    handler = configure_logging("json", stream=logs)
    try:
        with serve(create_app(services)) as url:
            yield Tokli(url, services, logs)
    finally:
        logging.getLogger().removeHandler(handler)
