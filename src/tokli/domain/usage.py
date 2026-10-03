"""Provider-reported usage of one forwarded request, in Tokli's categories (TM-003,
TOKLI_TELEMETRY_AND_COST §4)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Usage:
    source: str  # provider | provider_partial | unavailable
    reason: str | None = None  # usage_unavailable(<why>) when unavailable
    input: int | None = None
    cache_read: int | None = None
    cache_write_5m: int | None = None
    cache_write_1h: int | None = None
    output: int | None = None
    events: Mapping[str, int] = field(default_factory=dict)
    delta_fields: tuple[str, ...] = ()  # usage field names seen in message_delta (E4)

    @property
    def input_total(self) -> int | None:
        """Every input-side category; output never counts (TM-004)."""
        if self.input is None:
            return None
        return (
            self.input
            + (self.cache_read or 0)
            + (self.cache_write_5m or 0)
            + (self.cache_write_1h or 0)
        )
