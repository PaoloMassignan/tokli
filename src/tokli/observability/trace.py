"""Per-request traces and the bounded trace buffer (OB-002, OB-003).

A trace holds metadata only: span names, durations, outcomes, decisions and attributes. Callers
never put segment text, prompt content or credential values into it (OB-007, OB-008).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSpan:
    name: str
    offset_ms: float
    ms: float
    status: str = "ok"
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    request_id: str
    started: float  # perf_counter at arrival
    spans: list[TraceSpan] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)

    def span(self, name: str, start: float, end: float, status: str = "ok", **attrs: Any) -> None:
        self.spans.append(
            TraceSpan(
                name=name,
                offset_ms=(start - self.started) * 1000,
                ms=max(0.0, (end - start) * 1000),
                status=status,
                attrs=attrs,
            )
        )

    def decide(self, decision: str, reason: str) -> None:
        self.decisions.append({"decision": decision, "reason": reason})

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "spans": [
                {
                    "name": s.name,
                    "offset_ms": s.offset_ms,
                    "ms": s.ms,
                    "status": s.status,
                    "attrs": dict(s.attrs),
                }
                for s in self.spans
            ],
            "decisions": [dict(d) for d in self.decisions],
            "attrs": dict(self.attrs),
        }


class TraceBuffer:
    """The last ``capacity`` traces, by request id. Safe to use from several threads."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, request_id: str, entry: dict[str, Any]) -> None:
        with self._lock:
            self._items[request_id] = entry
            self._items.move_to_end(request_id)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._items.get(request_id)

    def __len__(self) -> int:
        return len(self._items)
