"""Whole-request estimates and calibration for one request (TM-004, TM-009; I1).

The whole-request estimate runs in a worker thread after the request was sent upstream, so it
never delays the client. Token counts are cached per text, so a conversation's unchanged history
costs almost nothing after the first request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from tokli.domain.models import CanonicalRequest, SegmentPlace
from tokli.domain.usage import Usage
from tokli.protocols.anthropic_messages import estimate_request_tokens, segment_places
from tokli.tokens.calibration import K_MAX, K_MIN, Calibration, OutlierWindow, calibrate
from tokli.tokens.counter import TokenCounter

__all__ = [
    "OUTLIER_RANGE",
    "Calibration",
    "OutlierWindow",
    "RequestEstimate",
    "TokenCounter",
    "calibrate_request",
    "estimate_request_tokens",
    "whole_request_estimates",
]


OUTLIER_RANGE = (K_MIN, K_MAX)  # a calibration factor outside it is an outlier (TM-009)


@dataclass(frozen=True)
class RequestEstimate:
    original: int
    forwarded: int
    started: float  # perf_counter
    ended: float
    places: tuple[SegmentPlace, ...] = ()  # TC-017: where each segment sits, provider order


def whole_request_estimates(
    request: CanonicalRequest, counter: TokenCounter, saved: int
) -> RequestEstimate:
    """The original request's estimate, and the forwarded one (``original - saved``: segment
    texts are counted one by one, so the mutable-scope saving carries over exactly), with the
    place of every segment (TC-017)."""
    started = time.perf_counter()
    original = estimate_request_tokens(request, counter.count)
    places = tuple(segment_places(request, counter.count)) if saved else ()
    return RequestEstimate(original, original - saved, started, time.perf_counter(), places)


def calibrate_request(
    usage: Usage, estimate: RequestEstimate | None, saved: int | None
) -> Calibration:
    return calibrate(
        usage.input_total if usage.source != "unavailable" else None,
        estimate.forwarded if estimate is not None else None,
        saved,
    )
