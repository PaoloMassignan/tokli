"""SPEC 015 (S3 endpoints), SPEC 016 (serving the dashboard): HTTP behaviour end to end."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.integration.servers import FakeUpstream, Tokli, make_config, run_tokli
from tokli.app.bootstrap import bootstrap
from tokli.compression.registry import REGISTRY

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contract" / "api"
REQUESTS = ROOT / "compat" / "fixtures" / "anthropic_messages"
UI = Path(__file__).resolve().parents[2] / "src" / "tokli" / "ui"
KEY = "sk-ant-api03-TOKLI-CANARY-KEY-SECRET"
HEADERS = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
ENDPOINTS = {
    "/tokli/api/requests": "requests_list",
    "/tokli/api/metrics/summary": "metrics_summary",
    "/tokli/api/metrics/timeseries?bucket=hour&from=": "metrics_timeseries",
    "/tokli/api/metrics/compressors": "metrics_compressors",
    "/tokli/api/compressors": "compressors",
}
Start = Callable[..., Tokli]


def usage_upstream(upstream: FakeUpstream) -> None:
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    async def responder(request: Request) -> Response:
        body = json.loads(await request.body())
        size = len(json.dumps(body)) // 4
        return JSONResponse(
            {"type": "message", "content": [], "usage": {"input_tokens": size, "output_tokens": 3}}
        )

    upstream.responder = responder


def traffic(tokli: Tokli) -> list[str]:
    ids = []
    for name in sorted(p.stem for p in REQUESTS.glob("*.json")):
        response = httpx.post(
            tokli.url + "/anthropic/v1/messages",
            content=(REQUESTS / f"{name}.json").read_bytes(),
            headers=HEADERS,
            timeout=10,
        )
        ids.append(response.headers["x-tokli-request-id"])
    for rid in ids:
        tokli.wait_trace(rid)
    assert tokli.services.store is not None
    tokli.services.store.flush()
    return ids


def url_of(path: str) -> str:
    if path.endswith("from="):  # two days of hourly buckets, ending now
        from datetime import UTC, datetime, timedelta

        return path + (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return path


def get(tokli: Tokli, path: str, **headers: str) -> httpx.Response:
    return httpx.get(tokli.url + url_of(path), headers=headers, timeout=10)


def validator(name: str) -> Draft202012Validator:
    resources = [
        (p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
        for p in SCHEMAS.glob("*.schema.json")
    ]
    registry: Registry = Registry().with_resources(resources)
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def test_api_contract_schemas_s3(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-API-1 / API-004: every S3 endpoint matches its JSON schema after real traffic."""
    usage_upstream(upstream)
    t = tokli()
    traffic(t)
    for path, schema in ENDPOINTS.items():
        response = get(t, path)
        assert response.status_code == 200, (path, response.text)
        errors = sorted(validator(schema).iter_errors(response.json()), key=str)
        assert errors == [], (path, [e.message for e in errors])


def _figures(node: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if "value" in node:
            found.append((path, node))
        for key, value in node.items():
            found.extend(_figures(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_figures(value, f"{path}/{i}"))
    return found


TOKEN_FIELDS = ("original", "forwarded", "saved", "tokens_in", "marginal_saved", "saving_pct")


def test_every_api_token_field_has_method_s3(tokli: Start, upstream: FakeUpstream) -> None:
    """API-002 / TM-005: each token figure carries a method, or is null with a reason."""
    usage_upstream(upstream)
    t = tokli()
    traffic(t)
    for path in ENDPOINTS:
        response = get(t, path)
        assert response.status_code == 200, path
        for where, figure in _figures(response.json()):
            if figure["value"] is None:
                assert "reason" in figure, (path, where)
            elif where.rsplit("/", 1)[-1] in TOKEN_FIELDS or "tokens_saved_per_ms" in where:
                assert figure.get("method") in ("exact", "calibrated", "estimate"), (path, where)


def test_api_returns_no_content_or_credentials_s3(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-API-2: canary scan over every new endpoint."""
    usage_upstream(upstream)
    t = tokli()
    traffic(t)
    responses = [get(t, path) for path in ENDPOINTS]
    assert all(r.status_code == 200 for r in responses)
    text = "".join(r.text for r in responses)
    assert "TOKLI-CANARY" not in text


def test_metrics_filters_validated_over_http(tokli: Start) -> None:
    response = get(tokli(), "/tokli/api/metrics/summary?tz=Mars/Olympus&from=yesterday")
    assert response.status_code == 400
    body = response.json()
    assert body["api_version"] == 1 and body["error"]["type"] == "invalid_parameter"
    assert set(body["error"]["fields"]) == {"tz", "from"}


def test_compressors_endpoint_read_only_metadata(tokli: Start) -> None:
    """P2: registry metadata, enabled and availability; no mutation in S3."""
    t = tokli()
    body = get(t, "/tokli/api/compressors").json()
    entry = next(c for c in body["compressors"] if c["id"] == REGISTRY[0].spec.id)
    assert entry["kind"] == "LOSSLESS" and entry["equivalence"] == "structural"
    assert entry["assumptions"] and entry["enabled"] is True
    assert entry["availability"] == "available"
    assert body["policy"] == "LOSSLESS_ONLY"
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        response = httpx.request(method, t.url + "/tokli/api/compressors", timeout=10)
        assert response.status_code == 405


@pytest.mark.parametrize(
    "path",
    ["/tokli/api/metrics/summary", "/tokli/api/requests", "/tokli/health", "/tokli/"],
)
def test_tokli_routes_reject_foreign_host(tokli: Start, path: str) -> None:
    """API-009 / AC-API-6: DNS-rebinding reads are refused."""
    t = tokli()
    assert get(t, path, host="evil.example").status_code == 403
    assert get(t, path, host="evil.example:" + t.url.rsplit(":", 1)[1]).status_code == 403
    port = t.url.rsplit(":", 1)[1]
    for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
        assert get(t, path, host=host).status_code == 200, host


def test_proxy_routes_ignore_host_check(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=(REQUESTS / "string_content.json").read_bytes(),
        headers={**HEADERS, "host": "api.anthropic.com"},
        timeout=10,
    )
    assert response.status_code == 200


def test_metrics_telemetry_disabled(tmp_path: Path, upstream: FakeUpstream) -> None:
    """API-011: without telemetry the metrics endpoints answer 503."""
    from tests.integration.servers import BYTE_CATALOG

    config = make_config(tmp_path, upstream.url)
    services = bootstrap(config, catalog=BYTE_CATALOG, version="test", telemetry=False)
    with run_tokli(config, services) as t:
        response = get(t, "/tokli/api/metrics/summary")
        assert response.status_code == 503
        assert response.json()["error"]["type"] == "telemetry_disabled"


def test_metrics_query_failure_isolated(
    tokli: Start,
    upstream: FakeUpstream,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """API-011: a failing query answers 500, logs one WARNING and leaves the proxy working."""
    from tokli.app import metrics

    def broken(self: object, *args: object) -> dict[str, Any]:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(metrics.MetricsQuery, "summary", broken)
    t = tokli()
    with caplog.at_level(logging.WARNING):
        response = get(t, "/tokli/api/metrics/summary")
    assert response.status_code == 500 and response.json()["error"]["type"] == "query_failed"
    assert "disk on fire" not in response.text
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "metrics" in r.name]
    assert len(warnings) == 1
    proxied = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=(REQUESTS / "string_content.json").read_bytes(),
        headers=HEADERS,
        timeout=10,
    )
    assert proxied.status_code == 200


# -- dashboard assets (SPEC 016) --------------------------------------------------------------

CONTENT_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
}


def ui_files() -> list[Path]:
    return sorted(p for p in UI.rglob("*") if p.suffix in CONTENT_TYPES)


def test_dashboard_served_at_tokli_root(tokli: Start) -> None:
    t = tokli()
    response = get(t, "/tokli/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/tokli/ui/" in response.text
    assert get(t, "/").status_code == 404  # still a Tokli unknown route


def test_ui_assets_served_with_explicit_content_types(tokli: Start) -> None:
    """AC-UI-5 / UI-011."""
    t = tokli()
    assert ui_files(), "no dashboard assets"
    for path in ui_files():
        relative = path.relative_to(UI).as_posix()
        if relative == "index.html":
            continue
        response = get(t, f"/tokli/ui/{relative}")
        assert response.status_code == 200, relative
        assert response.headers["content-type"].startswith(CONTENT_TYPES[path.suffix]), relative
    assert get(t, "/tokli/ui/../app/metrics.py").status_code == 404
    assert get(t, "/tokli/ui/missing.js").status_code == 404


def test_ui_has_no_compressor_specific_code() -> None:
    """AC-UI-1 / UI-001: the bundle knows API field names, never compressor ids."""
    ids = {c.spec.id for c in REGISTRY}
    for path in ui_files():
        text = path.read_text(encoding="utf-8")
        for cid in ids:
            assert cid not in text, (path.name, cid)


def test_ui_assets_load_offline() -> None:
    """AC-UI-4 / UI-006: no external resource is referenced (no CDN, no remote font)."""
    for path in ui_files():
        # The SVG namespace is an identifier, never fetched.
        text = path.read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "")
        for marker in ("http://", "https://", "//cdn", "@import url("):
            assert marker not in text, (path.name, marker)
