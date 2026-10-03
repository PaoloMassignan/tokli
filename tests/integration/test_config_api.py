"""SPEC 015 API-005…API-007, SPEC 017 CF-002/CF-005/CF-009 end to end (S4; ADR 0009)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tests.integration.servers import FakeUpstream, Tokli
from tests.unit.test_duplicate_pruning import FILE, conversation, results_of
from tokli.config.loader import UI_OVERRIDES_FILE

HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]


def patch(t: Tokli, changes: dict[str, Any], **headers: str) -> httpx.Response:
    return httpx.patch(
        t.url + "/tokli/api/config", json={"changes": changes}, headers=headers, timeout=10
    )


def send(t: Tokli, body: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(body).encode(),
        headers=HEADERS,
        timeout=10,
    )
    return t.wait_trace(response.headers["x-tokli-request-id"])


def setting(view: dict[str, Any], key: str) -> dict[str, Any]:
    return next(s for s in view["settings"] if s["key"] == key)


def test_get_config_lists_settings_with_sources_and_locks(tokli: Start) -> None:
    """CF-002 / API: every key with its value, source, editability and lock."""
    t = tokli(env={"TOKLI_TELEMETRY__RETENTION_DAYS": "10"})
    view = httpx.get(t.url + "/tokli/api/config", timeout=10).json()
    assert view["api_version"] == 1 and view["config_hash"] == t.services.config.config_hash
    minify = setting(view, "compressors.json_minify.enabled")
    assert minify == {
        "key": "compressors.json_minify.enabled",
        "value": True,
        "source": "default",
        "ui_editable": True,
        "locked_by": None,
    }
    retention = setting(view, "telemetry.retention_days")
    assert (
        retention["locked_by"] == "env:TOKLI_TELEMETRY__RETENTION_DAYS" and retention["value"] == 10
    )
    assert setting(view, "tokens.default")["ui_editable"] is False


def test_ui_toggle_changes_next_config_hash_and_attribution(
    tokli: Start, upstream: FakeUpstream
) -> None:
    """Roadmap exit / AC-API-5: switching the pruner (on by default since E11) off changes the
    next request's `config_hash`, what is forwarded, and the per-compressor attribution."""
    t = tokli()
    before = send(t, conversation(FILE, FILE))
    assert before["record"]["reference_stubs"] == 1
    assert {c["compressor_id"]: c for c in before["compressors"]}["duplicate_tool_results"][
        "accepted"
    ] == 1
    assert results_of(json.loads(upstream.received[-1].body))[1].startswith("[tokli: identical")
    response = patch(t, {"compressors.duplicate_tool_results.enabled": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["config_hash"] != before["record"]["config_hash"]
    assert setting(body, "compressors.duplicate_tool_results.enabled")["source"] == "ui"
    after = send(t, conversation(FILE, FILE))
    assert after["record"]["config_hash"] == body["config_hash"]
    assert after["record"]["reference_stubs"] == 0
    assert "duplicate_tool_results" not in {c["compressor_id"] for c in after["compressors"]}
    assert results_of(json.loads(upstream.received[-1].body))[1] == FILE


def test_patch_persists_to_ui_overrides_file(tokli: Start, tmp_path: Path) -> None:
    t = tokli()
    assert patch(t, {"telemetry.retention_days": 7}).status_code == 200
    stored = yaml.safe_load(
        (t.services.config.dirs.data_dir / UI_OVERRIDES_FILE).read_text(encoding="utf-8")
    )
    assert stored == {"telemetry": {"retention_days": 7}}
    assert t.services.store is not None and t.services.store.retention_days == 7
    reloaded = t.services.config.reload()
    assert reloaded.sources["telemetry.retention_days"] == "ui"


def test_patch_pinned_key_conflict(tokli: Start) -> None:
    """API-005 / AC-API-3."""
    t = tokli(env={"TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED": "true"})
    response = patch(t, {"compressors.json_minify.enabled": False})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["type"] == "locked" and error["key"] == "compressors.json_minify.enabled"
    assert error["source"] == "env:TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED"


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"compressors.nope.enabled": True}, "compressors.nope.enabled"),
        ({"tokens.default": "cl100k_base"}, "tokens.default"),
        ({"telemetry.retention_days": "seven"}, "telemetry.retention_days"),
        ({"telemetry.retention_days": -1}, "telemetry.retention_days"),
    ],
)
def test_patch_unknown_key_rejected(tokli: Start, changes: dict[str, Any], field: str) -> None:
    """API-005: unknown, not UI-editable, or invalid values → 400 naming the key; nothing
    changes."""
    t = tokli()
    before = t.services.config.config_hash
    response = patch(t, changes)
    assert response.status_code == 400
    assert field in response.json()["error"]["fields"]
    assert httpx.get(t.url + "/tokli/api/config", timeout=10).json()["config_hash"] == before
    assert not (t.services.config.dirs.data_dir / UI_OVERRIDES_FILE).exists()


def test_patch_rejects_malformed_body(tokli: Start) -> None:
    t = tokli()
    response = httpx.patch(t.url + "/tokli/api/config", content=b"not json", timeout=10)
    assert response.status_code == 400


def test_patch_noop_returns_same_hash(tokli: Start) -> None:
    t = tokli()
    first = patch(t, {"compressors.json_minify.enabled": True})
    assert first.status_code == 200 and first.json()["config_hash"] == t.services.config.config_hash


def test_mutation_rejects_foreign_origin(tokli: Start) -> None:
    """API-006 / AC-API-4."""
    t = tokli()
    foreign = patch(t, {"telemetry.retention_days": 9}, origin="https://evil.example")
    assert foreign.status_code == 403
    same = patch(t, {"telemetry.retention_days": 9}, origin=t.url)
    assert same.status_code == 200
    assert patch(t, {"telemetry.retention_days": 8}).status_code == 200  # no Origin: scripts


def test_config_change_atomic_snapshot(tokli: Start, upstream: FakeUpstream) -> None:
    """CF-005 / AC-API-5: a request in flight keeps the snapshot it started with."""
    gate = threading.Event()

    async def slow(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            yield b"event: ping\ndata: {}\n\n"
            await asyncio.to_thread(gate.wait, 5)
            yield b"event: message_stop\ndata: {}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream.responder = slow
    t = tokli()
    old_hash = t.services.config.config_hash
    body = json.dumps({**conversation(FILE, FILE), "stream": True}).encode()
    with httpx.stream(
        "POST", t.url + "/anthropic/v1/messages", content=body, headers=HEADERS, timeout=10
    ) as response:
        chunks = response.iter_raw()
        next(chunks)
        rid = response.headers["x-tokli-request-id"]
        assert patch(t, {"compressors.duplicate_tool_results.enabled": False}).status_code == 200
        gate.set()
        for _ in chunks:
            pass
    in_flight = t.wait_trace(rid)["record"]
    assert in_flight["config_hash"] == old_hash and in_flight["reference_stubs"] == 1

    async def plain(request: Request) -> Response:
        return JSONResponse({"type": "message", "content": []})

    upstream.responder = plain
    assert send(t, conversation(FILE, FILE))["record"]["config_hash"] != old_hash


def test_compressors_endpoint_shows_locks_and_evaluation(tokli: Start) -> None:
    """UI-003 / UI-005 / P5: evaluation status from the packaged (or repository) records."""
    t = tokli(env={"TOKLI_COMPRESSORS__DUPLICATE_TOOL_RESULTS__ENABLED": "false"})
    body = httpx.get(t.url + "/tokli/api/compressors", timeout=10).json()
    rows = {c["id"]: c for c in body["compressors"]}
    minify = rows["json_minify"]
    assert minify["locked_by"] is None
    assert minify["evaluation"] == {
        "status": "current",
        "tier": "smoke",
        "verdict": "no_measurable_damage",
        "model": "claude-opus-5-5",
        "date": "2026-10-03",
    }
    dup = rows["duplicate_tool_results"]
    assert dup["locked_by"] == "env:TOKLI_COMPRESSORS__DUPLICATE_TOOL_RESULTS__ENABLED"
    assert dup["evaluation"]["status"] in ("none", "current", "outdated")


def test_concurrent_patches_keep_every_change(
    tokli: Start, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API-007 (S4.5 D1, review A1): PATCHes that arrive together are applied one after the
    other, so none loses another's change.

    Root cause: `apply_patch` read the overrides file, merged and wrote it back with no lock
    over the whole sequence; only the snapshot swap was locked. Two PATCHes that both read
    before either wrote each wrote a file without the other's key. The barrier makes every
    PATCH read before any writes when nothing serialises them; when they are serialised, it
    times out and lets them run one by one."""
    import tokli.app.config_service as service

    changes: list[dict[str, Any]] = [
        {"compressors.json_minify.enabled": False},
        {"compressors.duplicate_tool_results.enabled": False},
        {"telemetry.retention_days": 5},
    ]
    barrier = threading.Barrier(len(changes))
    real_read = service.read_ui_overrides

    def read_together(path: Path) -> dict[str, object]:
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=1.0)
        return real_read(path)

    monkeypatch.setattr(service, "read_ui_overrides", read_together)
    t = tokli()
    results: list[httpx.Response] = []
    threads = [threading.Thread(target=lambda c=c: results.append(patch(t, c))) for c in changes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert [r.status_code for r in results] == [200] * len(changes), [r.text for r in results]
    view = httpx.get(t.url + "/tokli/api/config", timeout=10).json()
    for change in changes:
        for key, value in change.items():
            assert setting(view, key)["value"] == value and setting(view, key)["source"] == "ui"
    stored = yaml.safe_load(
        (t.services.config.dirs.data_dir / UI_OVERRIDES_FILE).read_text(encoding="utf-8")
    )
    assert stored == {
        "compressors": {
            "duplicate_tool_results": {"enabled": False},
            "json_minify": {"enabled": False},
        },
        "telemetry": {"retention_days": 5},
    }


def test_failed_write_leaves_no_temporary_file(
    tokli: Start, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API-007 (S4.5 D1): a write that fails answers 500, changes nothing and leaves no
    temporary file in the data directory.

    Root cause: the temporary file was written before `os.replace` and was not removed when
    the replace failed (on Windows, for example, while another process holds the target)."""
    import tokli.app.config_service as service

    def refuse(src: object, dst: object) -> None:
        raise PermissionError("target held open")

    monkeypatch.setattr(service.os, "replace", refuse)
    t = tokli()
    before = t.services.config.config_hash
    response = patch(t, {"telemetry.retention_days": 5})
    assert response.status_code == 500
    data_dir = t.services.config.dirs.data_dir
    assert sorted(p.name for p in data_dir.iterdir() if p.name.startswith(UI_OVERRIDES_FILE)) == []
    assert httpx.get(t.url + "/tokli/api/config", timeout=10).json()["config_hash"] == before
