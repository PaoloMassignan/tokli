"""Calibration of local estimates against provider usage (TM-004, TM-009, OB-011).

``k = exact input total / estimate of the whole forwarded request``. It turns an estimated saving
into provider units. Outside ``[K_MIN, K_MAX]`` the local tokenizer and the provider disagree too
much to trust it: the saving then stays an estimate.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

K_MIN = 0.5
K_MAX = 2.0
WINDOW = 100  # OB-011: the last 100 calibrated requests
MIN_SAMPLES = 20  # fewer calibrated requests than this: the health check stays ok (A8)
OUTLIER_SHARE = 0.20


@dataclass(frozen=True)
class Calibration:
    k: float | None
    status: str  # ok | outlier | unavailable
    reason: str | None  # calibration_outlier | calibration_unavailable
    saving: int | None
    method: str  # calibrated | estimate


def in_range(k: float | None) -> bool:
    return k is not None and K_MIN <= k <= K_MAX


def calibrated_value(value: int | None, k: float | None) -> tuple[int | None, str]:
    """``value * k`` labelled ``calibrated`` when ``k`` is in range, else the value as
    ``estimate`` (TM-005)."""
    if value is None:
        return None, "estimate"
    if in_range(k):
        assert k is not None
        return round(value * k), "calibrated"
    return value, "estimate"


def calibrate(
    exact_input_total: int | None, est_request_forwarded: int | None, est_saving: int | None
) -> Calibration:
    if exact_input_total is None or not est_request_forwarded:
        return Calibration(None, "unavailable", "calibration_unavailable", est_saving, "estimate")
    k = exact_input_total / est_request_forwarded
    saving, method = calibrated_value(est_saving, k)
    if in_range(k):
        return Calibration(k, "ok", None, saving, method)
    return Calibration(k, "outlier", "calibration_outlier", saving, method)


class OutlierWindow:
    """Outlier share over the last ``WINDOW`` calibrated requests (OB-011). Thread-safe."""

    def __init__(self) -> None:
        self._flags: deque[bool] = deque(maxlen=WINDOW)
        self._lock = threading.Lock()

    def add(self, *, outlier: bool) -> None:
        with self._lock:
            self._flags.append(outlier)

    def state(self) -> tuple[str, int, int]:
        """``(status, calibrated requests, outliers)``; status is ``ok`` or ``degraded``."""
        with self._lock:
            n, outliers = len(self._flags), sum(self._flags)
        degraded = n >= MIN_SAMPLES and outliers > OUTLIER_SHARE * n
        return ("degraded" if degraded else "ok", n, outliers)
