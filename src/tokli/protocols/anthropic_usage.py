"""Provider usage from Anthropic Messages responses (AN-005…AN-007, AN-009, AN-010).

The parsers read a passive copy of what is relayed: the relay hands them each chunk after it has
been passed on, and they never change it. Memory is bounded: a stream parser holds at most the
current event, a body parser at most the body, each up to ``limit`` bytes. Past the bound they stop
parsing and drop what they hold (AN-009).
"""

from __future__ import annotations

import json
from typing import Any

from tokli.domain.usage import Usage

# Events whose data carries usage, or ends the message.
_USAGE_EVENTS = frozenset({"message_start", "message_delta"})
_FIELDS = ("input", "cache_read", "cache_write_5m", "cache_write_1h", "output")


def unavailable(why: str, events: dict[str, int] | None = None) -> Usage:
    return Usage(source="unavailable", reason=f"usage_unavailable({why})", events=events or {})


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def map_usage(usage: Any) -> dict[str, int]:
    """Anthropic usage object → Tokli categories; absent fields are left out
    (TOKLI_TELEMETRY_AND_COST §4)."""
    if not isinstance(usage, dict):
        return {}
    mapped: dict[str, int] = {}
    for name, key in (
        ("input", "input_tokens"),
        ("cache_read", "cache_read_input_tokens"),
        ("output", "output_tokens"),
    ):
        value = _int(usage.get(key))
        if value is not None:
            mapped[name] = value
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        for name, key in (
            ("cache_write_5m", "ephemeral_5m_input_tokens"),
            ("cache_write_1h", "ephemeral_1h_input_tokens"),
        ):
            value = _int(split.get(key))
            if value is not None:
                mapped[name] = value
    else:
        created = _int(usage.get("cache_creation_input_tokens"))
        if created is not None:  # no split reported: all of it counts as 5m
            mapped["cache_write_5m"] = created
            mapped["cache_write_1h"] = 0
    return mapped


def _usage(
    source: str,
    values: dict[str, int],
    events: dict[str, int],
    delta_fields: tuple[str, ...] = (),
) -> Usage:
    if "input" in values:  # the other input categories are 0 when the provider omits them
        for name in ("cache_read", "cache_write_5m", "cache_write_1h"):
            values.setdefault(name, 0)
    return Usage(
        source=source,
        input=values.get("input"),
        cache_read=values.get("cache_read"),
        cache_write_5m=values.get("cache_write_5m"),
        cache_write_1h=values.get("cache_write_1h"),
        output=values.get("output"),
        events=dict(events),
        delta_fields=delta_fields,
    )


class StreamUsageParser:
    """Incremental SSE decoder. Lines may end in LF, CR LF or CR, and events may be split
    anywhere across chunks."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._pending = bytearray()  # the unterminated tail of the stream
        self._event = ""
        self._data: list[bytes] = []
        self._data_size = 0
        self._events: dict[str, int] = {}
        self._values: dict[str, int] = {}
        self._started = False
        self._final = False
        self._delta_fields: set[str] = set()
        self._failure: str | None = None

    @property
    def buffered_bytes(self) -> int:
        return len(self._pending) + self._data_size

    def feed(self, chunk: bytes) -> None:
        if self._failure is not None or not chunk:
            return
        self._pending += chunk
        start = 0
        pending = self._pending
        end = len(pending)
        while start < end:
            lf = pending.find(b"\n", start)
            cr = pending.find(b"\r", start, lf if lf >= 0 else end)
            if cr >= 0:
                if cr + 1 == end:
                    break  # a CR at the end may be the first half of CR LF: wait for more
                line_end, next_start = cr, cr + (2 if pending[cr + 1 : cr + 2] == b"\n" else 1)
            elif lf >= 0:
                line_end, next_start = lf, lf + 1
            else:
                break
            self._line(bytes(pending[start:line_end]))
            start = next_start
            if self._failure is not None:
                return
        del pending[:start]
        if self.buffered_bytes > self._limit:
            self._fail("buffer_limit")

    def _fail(self, why: str) -> None:
        self._failure = why
        self._pending = bytearray()
        self._data = []
        self._data_size = 0

    def _line(self, line: bytes) -> None:
        if not line:
            self._dispatch()
            return
        if line.startswith(b":"):
            return
        name, _, value = line.partition(b":")
        if value.startswith(b" "):
            value = value[1:]
        if name == b"event":
            self._event = value.decode("utf-8", "replace")
        elif name == b"data" and (self._event in _USAGE_EVENTS or self._event == ""):
            # Only usage-bearing (or unnamed) events keep their data; others are counted only.
            self._data.append(value)
            self._data_size += len(value)
            if self._data_size > self._limit:
                self._fail("buffer_limit")

    def _dispatch(self) -> None:
        event, data = self._event, b"\n".join(self._data)
        self._event, self._data, self._data_size = "", [], 0
        payload: Any = None
        if data and (event in _USAGE_EVENTS or event == ""):
            try:
                payload = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                if event in _USAGE_EVENTS:
                    self._fail("parse_error")
                    return
            if not event and isinstance(payload, dict):
                event = str(payload.get("type", ""))
        if not event:
            return
        self._events[event] = self._events.get(event, 0) + 1
        if not isinstance(payload, dict):
            return
        if event == "message_start":
            message = payload.get("message")
            values = map_usage(message.get("usage") if isinstance(message, dict) else None)
            if values:
                self._started = True
                self._values.update(values)
        elif event == "message_delta":
            raw = payload.get("usage")
            if isinstance(raw, dict):
                self._delta_fields.update(str(name) for name in raw)
            values = map_usage(raw)
            if (
                isinstance(raw, dict)
                and not isinstance(raw.get("cache_creation"), dict)
                and values.get("cache_write_5m")
                == self._values.get("cache_write_5m", 0) + self._values.get("cache_write_1h", 0)
            ):
                # The delta repeats the cache-write total without its 5m/1h split: keep the
                # split from message_start (E4, 2026-10-03).
                values.pop("cache_write_5m")
                values.pop("cache_write_1h", None)
            if values:
                self._final = True
                self._values.update(values)  # the last non-null value per field wins

    def result(self, *, disconnected: bool = False) -> Usage:
        if self._failure is None and self._pending.endswith(b"\r"):
            # The stream ended: a trailing CR is a complete line ending after all.
            line, self._pending = bytes(self._pending[:-1]), bytearray()
            self._line(line)
        if self._failure is not None:
            return unavailable(self._failure, self._events)
        fields = tuple(sorted(self._delta_fields))
        if self._final and self._started:
            return _usage("provider", self._values, self._events, fields)
        if self._started:
            return _usage("provider_partial", self._values, self._events, fields)
        return unavailable("client_disconnected" if disconnected else "no_usage", self._events)


class BodyUsageParser:
    """Collects a non-streaming JSON body up to the bound and reads its ``usage``."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._body = bytearray()
        self._failure: str | None = None

    @property
    def buffered_bytes(self) -> int:
        return len(self._body)

    def feed(self, chunk: bytes) -> None:
        if self._failure is not None:
            return
        self._body += chunk
        if len(self._body) > self._limit:
            self._failure = "buffer_limit"
            self._body = bytearray()

    def result(self, *, disconnected: bool = False) -> Usage:
        if self._failure is not None:
            return unavailable(self._failure)
        if disconnected:
            return unavailable("client_disconnected")
        try:
            payload = json.loads(self._body)
        except (ValueError, UnicodeDecodeError):
            return unavailable("parse_error")
        values = map_usage(payload.get("usage") if isinstance(payload, dict) else None)
        if "input" not in values:
            return unavailable("no_usage")
        return _usage("provider", values, {})
