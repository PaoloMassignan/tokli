"""`duplicate_tool_results` through the real proxy (SPEC 019, TC-014, CC-002 after SCR-001)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from tests.integration.servers import FakeUpstream, Tokli
from tests.unit.test_duplicate_pruning import FILE, conversation, results_of, stub_for

HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]


def send(t: Tokli, body: dict[str, object]) -> dict[str, object]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(body).encode(),
        headers=HEADERS,
        timeout=10,
    )
    return t.wait_trace(response.headers["x-tokli-request-id"])


def test_duplicate_pruning_can_be_switched_off(tokli: Start, upstream: FakeUpstream) -> None:
    """On by default since E11 (CC-020); switched off, nothing is stubbed."""
    t = tokli("compressors.duplicate_tool_results.enabled=false")
    view = send(t, conversation(FILE, FILE))
    assert results_of(json.loads(upstream.received[-1].body)) == [FILE, FILE]
    assert view["record"]["reference_stubs"] == 0
    assert view["record"]["policy"] == "LOSSLESS_ONLY"


def test_duplicate_pruning_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli("compressors.duplicate_tool_results.enabled=true")
    view = send(t, conversation(FILE, FILE, FILE))
    forwarded = json.loads(upstream.received[-1].body)
    first, *later = results_of(forwarded)
    assert first == FILE
    # the token count in the stub comes from the real tokenizer here, not the test counter
    assert all(r.startswith(stub_for("toolu_00", FILE).split(" — ")[0]) for r in later)
    assert len(later) == 2
    record = view["record"]
    assert record["reference_stubs"] == 2 and record["outcome"] == "compressed"
    assert record["policy"] == "LOSSLESS_ONLY"
    stats = {c["compressor_id"]: c for c in view["compressors"]}
    assert stats["duplicate_tool_results"]["accepted"] == 2
    assert stats["duplicate_tool_results"]["marginal_saved"] > 0
    assert t.services.store is not None
    t.services.store.flush()
    stored = t.services.store.get(view["request_id"])
    assert stored is not None and stored["record"]["reference_stubs"] == 2
