"""In-memory conversation state for request-scope pruners (SPEC 019 PR-021…PR-024, PR-027,
ADR 0012): per conversation key, the time of its last request, that request's cache lifetime and
the tool calls pruned at its last resume. Bounded (least recently used), thread-safe, never
written to disk. The store also decides whether a request is a resume (S8i SCR-001)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from tokli.domain.models import CanonicalRequest, Patch
from tokli.domain.stage import ConversationView

PRUNER_ID = "edit_args_on_resume"
DEFAULT_TTLS: Mapping[str, float] = {"anthropic_messages": 3600.0}  # SPEC 017 defaults


@dataclass(frozen=True)
class _Entry:
    seen: float
    cache_ttl_s: float | None
    pruned: frozenset[str]


class ConversationStore:
    def __init__(
        self,
        capacity: int = 1024,
        clock: Callable[[], float] = time.time,
        *,
        ttl_defaults: Mapping[str, float] | None = None,
        margin_s: float = 60.0,
    ) -> None:
        self._capacity = capacity
        self.clock = clock  # wall clock: a sleeping machine still counts the pause (ADR 0012)
        self._ttl_defaults = dict(DEFAULT_TTLS if ttl_defaults is None else ttl_defaults)
        self._margin_s = margin_s
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def view(self, key: str, protocol: str) -> ConversationView:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return ConversationView(True)  # PR-021: an unknown conversation is a resume
            self._entries.move_to_end(key)
            since = max(0.0, self.clock() - entry.seen)
        if entry.cache_ttl_s is not None:  # PR-027
            ttl, source = entry.cache_ttl_s, "previous_request"
        else:
            ttl, source = self._ttl_defaults[protocol], "protocol_default"
        return ConversationView(
            is_resume=since > ttl + self._margin_s,  # PR-021
            pruned_call_ids=entry.pruned,
            seconds_since_last=since,
            cache_ttl_s=ttl,
            cache_ttl_source=source,
        )

    def record(
        self, key: str, pruned_call_ids: Iterable[str], cache_ttl_s: float | None = None
    ) -> bool:
        """Stores the request; returns whether calls were newly pruned (``history_rewritten``)."""
        pruned = frozenset(pruned_call_ids)
        with self._lock:
            previous = self._entries.pop(key, None)
            self._entries[key] = _Entry(self.clock(), cache_ttl_s, pruned)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return bool(pruned - (previous.pruned if previous is not None else frozenset()))

    def touch(self, key: str, at: float) -> None:
        """A successful keepalive request at ``at`` (SPEC 020 KA-013): the conversation was
        last seen then; its cache lifetime and pruned calls stay those of its last request
        (PR-021, PR-024 after S8l SCR-001; ADR 0012 amendment 3)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and at > entry.seen:
                self._entries[key] = _Entry(at, entry.cache_ttl_s, entry.pruned)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


def pruned_call_ids(request: CanonicalRequest, patches: Sequence[Patch]) -> frozenset[str]:
    """The tool calls whose arguments the forwarded request carries as stubs."""
    ids = set()
    for patch in patches:
        if PRUNER_ID in patch.produced_by:
            call_id = request.segment(patch.segment_id).tool_call_id
            if call_id is not None:
                ids.add(call_id)
    return frozenset(ids)
