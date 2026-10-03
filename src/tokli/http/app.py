"""The Starlette application. Routes only; the proxy flow lives in ``tokli.http.proxy``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from tokli.app.api import API_VERSION, request_view
from tokli.app.bootstrap import Services
from tokli.http.proxy import PREFIX, ProxyHandler
from tokli.observability.ids import new_request_id

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def create_app(services: Services, listen: str | None = None) -> Starlette:
    proxy = ProxyHandler(services)

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
        server = services.config.settings.server
        return JSONResponse(
            {
                "status": "degraded" if degraded else "ok",
                "version": services.version,
                "listen": listen or f"{server.host}:{server.port}",
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

    return Starlette(
        routes=[
            Route("/tokli/health", health, methods=["GET"]),
            Route("/tokli/api/requests/{request_id}", request_detail, methods=["GET"]),
            Route(PREFIX, proxy.handle, methods=_METHODS),
            Route(PREFIX + "/{path:path}", proxy.handle, methods=_METHODS),
            Route("/{path:path}", unknown, methods=_METHODS),
        ],
        lifespan=lifespan,
    )
