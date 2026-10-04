"""In-memory conversation state for request-scope pruners (SPEC 019 PR-021…PR-024, ADR 0012):
per conversation key, the time of its last request and the tool calls pruned at its last resume.
Bounded (least recently used), thread-safe, never written to disk."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence

from tokli.domain.models import CanonicalRequest, Patch
from tokli.domain.stage import ConversationView

PRUNER_ID = "edit_args_on_resume"


class ConversationStore:
    def __init__(self, capacity: int = 1024, clock: Callable[[], float] = time.time) -> None:
        self._capacity = capacity
        self.clock = clock  # wall clock: a sleeping machine still counts the pause (ADR 0012)
        self._entries: OrderedDict[str, tuple[float, frozenset[str]]] = OrderedDict()
        self._lock = threading.Lock()

    def view(self, key: str) -> ConversationView:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return ConversationView(None)
            self._entries.move_to_end(key)
            return ConversationView(max(0.0, self.clock() - entry[0]), entry[1])

    def record(self, key: str, pruned_call_ids: Iterable[str]) -> bool:
        """Stores the request; returns whether calls were newly pruned (``history_rewritten``)."""
        pruned = frozenset(pruned_call_ids)
        with self._lock:
            previous = self._entries.pop(key, None)
            self._entries[key] = (self.clock(), pruned)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return bool(pruned - (previous[1] if previous is not None else frozenset()))

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
