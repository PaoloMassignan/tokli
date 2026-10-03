"""The Starlette application. Routes only; the proxy flow lives in ``tokli.http.proxy`` and the
use cases in ``tokli.app`` (API-008)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from tokli.app.api import API_VERSION, compressors_view, request_view
from tokli.app.bootstrap import Services
from tokli.app.metrics import InvalidParameters, MetricsQuery, parse_filters
from tokli.http.proxy import PREFIX, ProxyHandler
from tokli.observability.ids import new_request_id

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_LOG = logging.getLogger("tokli.metrics")
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
# Explicit content types (UI-011): never the host's file-type registry, which on some Windows
# machines maps .js to text/plain.
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
_LOOPBACK = ("127.0.0.1", "localhost", "[::1]", "::1")
_WILDCARD = ("0.0.0.0", "::", "[::]", "")


def allowed_hosts(listen: str) -> Callable[[str], bool]:
    """The `Host` values accepted under ``/tokli/`` (API-009)."""
    host, _, port = listen.rpartition(":")
    if host in _WILDCARD:  # only possible with --allow-remote: only the port can be checked
        return lambda value: value.rpartition(":")[2] == port
    names = {host, *_LOOPBACK} if host in _LOOPBACK else {host}
    accepted = {f"{name}:{port}" for name in names if name != "::1"}
    if port == "80":
        accepted |= names
    return lambda value: value.lower() in accepted


class TokliHostCheck:
    """403 for `/tokli/*` requests whose `Host` is not Tokli's own address (DNS rebinding).
    Proxy routes are untouched: their `Host` belongs to the client's view of the provider."""

    def __init__(self, app: ASGIApp, accept: Callable[[str], bool]) -> None:
        self._app = app
        self._accept = accept

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and (
            scope["path"] == "/tokli" or scope["path"].startswith("/tokli/")
        ):
            host = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
            if not self._accept(host):
                response = JSONResponse(
                    {"api_version": API_VERSION, "error": {"type": "forbidden_host"}},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def _error(status: int, kind: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        {"api_version": API_VERSION, "error": {"type": kind, **extra}}, status_code=status
    )


def get_only(
    handler: Callable[[Request], Awaitable[Response]],
) -> Callable[[Request], Awaitable[Response]]:
    """Read-only endpoints answer 405 to other methods (instead of the catch-all 404)."""

    async def wrapped(request: Request) -> Response:
        if request.method not in ("GET", "HEAD"):
            return _error(405, "method_not_allowed")
        return await handler(request)

    return wrapped


def create_app(services: Services, listen: str | None = None) -> ASGIApp:
    proxy = ProxyHandler(services)
    server = services.config.settings.server
    listen = listen or f"{server.host}:{server.port}"
    metrics = (
        MetricsQuery(
            services.store.path,
            budget_ms=services.config.settings.compression.request_budget_ms,
        )
        if services.store is not None
        else None
    )

    async def health(request: Request) -> Response:
        store = services.store
        telemetry = "disabled" if store is None else ("ok" if store.healthy else "failing")
        unavailable = [
            cid
            for cid, state in services.availability.items()
            if services.enabled.get(cid) and state != "available"
        ]
        compressors = "ok" if not unavailable else "unavailable: " + ", ".join(sorted(unavailable))
        state, calibrated, outliers = services.calibration.state()  # OB-011
        calibration = "ok" if state == "ok" else f"outliers: {outliers} of {calibrated}"
        degraded = telemetry == "failing" or bool(unavailable) or state != "ok"
        return JSONResponse(
            {
                "status": "degraded" if degraded else "ok",
                "version": services.version,
                "listen": listen,
                "checks": {
                    "telemetry": telemetry,
                    "compressors": compressors,
                    "calibration": calibration,
                },
            }
        )

    async def request_detail(request: Request) -> Response:
        request_id = request.path_params["request_id"]
        entry = services.traces.get(request_id)
        if entry is None and services.store is not None:
            stored = services.store.get(request_id)
            if stored is not None:
                entry = request_view(stored["record"], stored["compressors"], None)
        if entry is None:
            return JSONResponse(
                {
                    "api_version": API_VERSION,
                    "error": {"type": "not_found", "request_id": request_id},
                },
                status_code=404,
            )
        return JSONResponse(entry)

    def metrics_endpoint(
        run: Callable[[MetricsQuery, dict[str, str]], dict[str, Any]],
    ) -> Callable[[Request], Awaitable[Response]]:
        async def endpoint(request: Request) -> Response:
            query = metrics
            if query is None:
                return _error(503, "telemetry_disabled")
            params = dict(request.query_params)
            try:
                body = await anyio.to_thread.run_sync(lambda: run(query, params))
            except InvalidParameters as exc:
                return _error(400, "invalid_parameter", fields=exc.fields)
            except Exception as exc:  # API-011: a failing query never affects the proxy
                _LOG.warning(
                    "metrics query failed",
                    extra={"tokli": {"event": "metrics_failure", "error": type(exc).__name__}},
                )
                return _error(500, "query_failed")
            return JSONResponse(body)

        return get_only(endpoint)

    summary = metrics_endpoint(lambda q, p: q.summary(parse_filters(p)))
    timeseries = metrics_endpoint(lambda q, p: q.timeseries(parse_filters(p)))
    compressor_metrics = metrics_endpoint(lambda q, p: q.compressors(parse_filters(p)))

    def _list(q: MetricsQuery, p: dict[str, str]) -> dict[str, Any]:
        f = parse_filters(p)
        return q.requests(f.limit, f.cursor)

    requests_list = metrics_endpoint(_list)

    @get_only
    async def compressors(request: Request) -> Response:
        return JSONResponse(compressors_view(services.enabled, services.availability))

    @get_only
    async def dashboard(request: Request) -> Response:
        return FileResponse(UI_DIR / "index.html", media_type=_CONTENT_TYPES[".html"])

    @get_only
    async def ui_asset(request: Request) -> Response:
        relative = request.path_params["path"]
        target = (UI_DIR / relative).resolve()
        media_type = _CONTENT_TYPES.get(target.suffix)
        if media_type is None or not target.is_relative_to(UI_DIR) or not target.is_file():
            return _error(404, "not_found")
        return FileResponse(target, media_type=media_type)

    async def unknown(request: Request) -> Response:
        rid = new_request_id()
        return JSONResponse(
            {
                "error": {
                    "type": "tokli_unknown_route",
                    "source": "tokli",
                    "message": f"no route for {request.url.path}; configured prefixes: {PREFIX}",
                    "request_id": rid,
                }
            },
            status_code=404,
            headers={"x-tokli-request-id": rid},
        )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        await services.upstream.start()
        if services.store is not None:
            services.store.start()
        try:
            yield
        finally:
            await services.upstream.aclose()
            if services.store is not None:
                services.store.close()

    app = Starlette(
        routes=[
            Route("/tokli/health", health, methods=["GET"]),
            Route("/tokli/", dashboard, methods=_METHODS),
            Route("/tokli/ui/{path:path}", ui_asset, methods=_METHODS),
            Route("/tokli/api/requests", requests_list, methods=_METHODS),
            Route("/tokli/api/requests/{request_id}", request_detail, methods=["GET"]),
            Route("/tokli/api/metrics/summary", summary, methods=_METHODS),
            Route("/tokli/api/metrics/timeseries", timeseries, methods=_METHODS),
            Route("/tokli/api/metrics/compressors", compressor_metrics, methods=_METHODS),
            Route("/tokli/api/compressors", compressors, methods=_METHODS),
            Route(PREFIX, proxy.handle, methods=_METHODS),
            Route(PREFIX + "/{path:path}", proxy.handle, methods=_METHODS),
            Route("/{path:path}", unknown, methods=_METHODS),
        ],
        lifespan=lifespan,
    )
    return TokliHostCheck(app, allowed_hosts(listen))
