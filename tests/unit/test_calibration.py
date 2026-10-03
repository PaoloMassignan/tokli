"""TM-004, TM-009, OB-011 (window): calibration factor, outliers, whole-request estimate."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from tokli.domain.models import SegmentKind
from tokli.protocols.anthropic_messages import estimate_request_tokens, parse
from tokli.tokens.calibration import OutlierWindow, calibrate

MUTABLE = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})


def test_calibration_factor() -> None:
    """AC-TM-5: usage 1,100 vs estimate 1,000 → k = 1.1; 100 saved → 110 calibrated."""
    result = calibrate(exact_input_total=1100, est_request_forwarded=1000, est_saving=100)
    assert result.k == pytest.approx(1.1)
    assert result.status == "ok"
    assert result.saving == 110 and result.method == "calibrated"


def test_calibration_outlier_falls_back_to_estimate() -> None:
    """AC-TM-5 / TM-009: k = 3 → the saving stays an estimate and the outlier is flagged."""
    result = calibrate(exact_input_total=3000, est_request_forwarded=1000, est_saving=100)
    assert result.k == pytest.approx(3.0)
    assert result.status == "outlier" and result.reason == "calibration_outlier"
    assert result.saving == 100 and result.method == "estimate"


@pytest.mark.parametrize("exact, estimate", [(500, 1000), (2000, 1000)])
def test_calibration_range_is_inclusive(exact: int, estimate: int) -> None:
    assert calibrate(exact, estimate, 10).status == "ok"


@pytest.mark.parametrize("exact, estimate", [(None, 1000), (1000, None), (1000, 0)])
def test_calibration_unavailable(exact: int | None, estimate: int | None) -> None:
    result = calibrate(exact, estimate, 100)
    assert result.k is None
    assert result.status == "unavailable" and result.reason == "calibration_unavailable"
    assert result.saving == 100 and result.method == "estimate"


def test_calibration_without_saving_estimate() -> None:
    result = calibrate(1100, 1000, None)
    assert result.k == pytest.approx(1.1) and result.saving is None


def test_passthrough_request_is_calibrated_with_zero_saving() -> None:
    """A6: k is computed even when nothing was saved."""
    result = calibrate(1100, 1000, 0)
    assert result.status == "ok" and result.saving == 0 and result.method == "calibrated"


def test_outlier_window() -> None:
    """OB-011 / A8: over the last 100 calibrated requests; fewer than 20 → ok."""
    window = OutlierWindow()
    for _ in range(19):
        window.add(outlier=True)
    assert window.state() == ("ok", 19, 19)
    window.add(outlier=True)
    assert window.state()[0] == "degraded"
    for _ in range(100):
        window.add(outlier=False)
    assert window.state() == ("ok", 100, 0)
    for _ in range(20):
        window.add(outlier=True)
    assert window.state() == ("ok", 100, 20)  # exactly 20 % is not "more than 20 %"
    window.add(outlier=True)
    assert window.state() == ("degraded", 100, 21)


def _request_with_binary_payloads(data: str, signature: str) -> dict[str, Any]:
    return {
        "model": "claude-test",
        "max_tokens": 10,
        "messages": [
            {"role": "user", "content": "look at this"},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "plan", "signature": signature},
                    {"type": "redacted_thinking", "data": signature},
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"p": "a.png"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [
                            {"type": "text", "text": "an image"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": data,
                                },
                            },
                        ],
                    },
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                    },
                ],
            },
        ],
    }


def byte_count(text: str) -> int:
    return len(text.encode("utf-8"))


def test_whole_request_estimate_excludes_binary_payloads() -> None:
    """AC-TM-7: binary payloads count nothing; text and structure count."""
    heavy = _request_with_binary_payloads("A" * 1_000_000, "S" * 50_000)
    light = _request_with_binary_payloads("", "")
    estimate = estimate_request_tokens(
        parse(json.dumps(heavy).encode(), mutable_kinds=MUTABLE), byte_count
    )
    assert estimate == estimate_request_tokens(
        parse(json.dumps(light).encode(), mutable_kinds=MUTABLE), byte_count
    )
    assert 0 < estimate < 2000

    longer = copy.deepcopy(light)
    longer["messages"][0]["content"] = "look at this" + "!" * 10
    assert (
        estimate_request_tokens(
            parse(json.dumps(longer).encode(), mutable_kinds=MUTABLE), byte_count
        )
        == estimate + 10
    )


def test_whole_request_estimate_counts_every_segment_text() -> None:
    body = {
        "model": "m",
        "system": "S" * 300,
        "tools": [{"name": "t", "description": "D" * 400, "input_schema": {"type": "object"}}],
        "messages": [{"role": "user", "content": "U" * 500}],
    }
    request = parse(json.dumps(body).encode(), mutable_kinds=MUTABLE)
    estimate = estimate_request_tokens(request, byte_count)
    assert estimate >= 300 + 400 + 500
