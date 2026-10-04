"""``duplicate_tool_results`` (SPEC 019, S4): a later tool result whose text is byte-identical
to an earlier one is replaced by a stub naming the earlier call. LOSSLESS by reference: the
original text stays in the request, in the earliest copy (PR-002, PR-003). The plan for a
segment reads only that segment and the ones before it (prefix-stable, PR-004)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence

from tokli.compression.contract import (
    CompressorSpec,
    Proposal,
    SegmentRef,
    ToolRecordView,
)
from tokli.domain.models import SegmentKind
from tokli.domain.stage import ConversationView

STUB_PREFIX = "[tokli: identical to the result of tool call "
_STUB = STUB_PREFIX + "{call_id} earlier in this conversation — {tokens} tokens omitted]"
_STUB_LINE = re.compile(
    re.escape(STUB_PREFIX) + r"(?P<call_id>\S+) earlier in this conversation — \d+ tokens omitted\]"
)

SPEC = CompressorSpec(
    id="duplicate_tool_results",
    name="Duplicate tool results",
    version="1",
    kind="LOSSLESS",
    equivalence="reference",
    scope="request",
    prefix_stable=True,
    guarantees=(
        "whole-request decode restores every original text "
        "(prop_duplicate_pruning_decodes_whole_request)",
        "the target precedes the stub and keeps its content "
        "(test_reference_target_integrity_enforced)",
        "prefix stability (test_duplicate_pruning_prefix_stable_across_turns)",
        "structure, ids and arguments unchanged (test_pruning_preserves_structure_and_arguments)",
    ),
    assumptions=("resolves_result_reference", "quotes_from_reference_target"),
    stage="structural",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT}),
    min_tokens=0,  # the pruner applies its own `pruning.duplicate_min_tokens`
    cost_class="cheap",
    terminal=True,  # a stub is final: nothing else may change it
    requires=(),
    default_enabled=True,  # smoke record (E11, 2026-10-03): no_measurable_damage (CC-020)
)


def _canonical(arguments: object) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class DuplicateToolResults:
    spec = SPEC

    def __init__(self, min_tokens: int = 64, require_same_call: bool = False) -> None:
        self._min_tokens = min_tokens
        self._require_same_call = require_same_call

    def plan(
        self,
        refs: Sequence[SegmentRef],
        texts: Mapping[str, str],
        tools: Sequence[ToolRecordView],
        count: Callable[[str], int],
        conversation: ConversationView | None = None,  # unused: prefix-stable by itself
    ) -> list[Proposal]:
        calls = {t.call_id: (t.name, _canonical(t.arguments)) for t in tools}
        earliest: dict[str, SegmentRef] = {}
        proposals: list[Proposal] = []
        for ref in refs:  # document order: segment j sees only segments 0..j
            sid = ref.segment_id
            if ref.view.kind is not SegmentKind.TOOL_RESULT or ref.call_id is None:
                proposals.append(Proposal(sid, None, reason="no_call_id"))
                continue
            if not ref.whole_result:  # PR-015: whole results only, as stub and as target
                proposals.append(Proposal(sid, None, reason="multi_block"))
                continue
            text = texts[sid]
            target = earliest.get(text)
            if target is None:
                earliest[text] = ref
                proposals.append(Proposal(sid, None, reason="no_earlier_copy"))
                continue
            if self._require_same_call and calls.get(ref.call_id) != calls.get(
                target.call_id or ""
            ):
                proposals.append(Proposal(sid, None, reason="not_same_call"))
                continue
            tokens = count(text)
            if tokens < self._min_tokens:
                proposals.append(Proposal(sid, None, reason="small_duplicate"))
                continue
            stub = _STUB.format(call_id=target.call_id, tokens=tokens)
            kept = "".join("\n" + text[s.start : s.end] for s in ref.view.protected)  # PR-015
            proposals.append(Proposal(ref.segment_id, stub + kept, target.segment_id))
        return proposals

    def decode_request(
        self, texts: Mapping[str, str], refs: Sequence[SegmentRef]
    ) -> dict[str, str]:
        """Each stub → the text of the result it names (whole-request decode, PR-003)."""
        by_call = {r.call_id: r.segment_id for r in refs if r.call_id is not None}
        decoded: dict[str, str] = {}
        for segment_id, text in texts.items():
            match = _STUB_LINE.match(text)
            target = by_call.get(match.group("call_id")) if match else None
            if target is not None:
                decoded[segment_id] = texts[target]
        return decoded
