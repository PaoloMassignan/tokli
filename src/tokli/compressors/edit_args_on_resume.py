"""``edit_args_on_resume``: when a conversation resumes after its provider cache expired, replace
the strings of old ``Write``/``Edit`` arguments with a stub, and keep that replacement until the
next resume (SPEC 019 PR-020…PR-026, ADR 0012). SELECTIVE, request scope."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from tokli.compression.contract import CompressorSpec, Proposal, SegmentRef, ToolRecordView
from tokli.domain.models import SegmentKind
from tokli.domain.stage import ConversationView

SPEC = CompressorSpec(
    id="edit_args_on_resume",
    name="Old edit content at resume",
    version="1",
    kind="SELECTIVE",
    equivalence="none",
    scope="request",
    prefix_stable=False,
    guarantees=(
        "keys, file paths, ids and structure unchanged "
        "(test_resume_pruning_keeps_structure_and_paths)",
        "byte-identical prefix between resumes (test_resume_pruning_stable_between_resumes)",
        "only old calls, only at a resume (test_resume_pruning_only_at_resume_and_old_calls)",
    ),
    assumptions=("edit_content_not_needed",),
    stage="structural",
    segment_kinds=frozenset({SegmentKind.TOOL_CALL_ARGS}),
    min_tokens=0,
    cost_class="cheap",
    terminal=False,
    requires=(),
    default_enabled=False,
)


STUB = (
    "[tokli: earlier edit content omitted ({tokens} tokens) — read the file for its current state]"
)


class EditArgsOnResume:
    spec = SPEC

    def __init__(
        self, resume_after_s: float = 3600.0, min_age_turns: int = 4, min_tokens: int = 64
    ) -> None:
        self._resume_after_s = resume_after_s
        self._min_age_turns = min_age_turns
        self._min_tokens = min_tokens

    def plan(
        self,
        refs: Sequence[SegmentRef],
        texts: Mapping[str, str],
        tools: Sequence[ToolRecordView],
        count: Callable[[str], int],
        conversation: ConversationView | None = None,
    ) -> list[Proposal]:
        since = conversation.seconds_since_last if conversation is not None else None
        resume = since is None or since > self._resume_after_s  # PR-021 (unknown: resume, P5)
        stored = conversation.pruned_call_ids if conversation is not None else frozenset()
        turns = {t.call_id: t.human_turns_after for t in tools}
        proposals: list[Proposal] = []
        for ref in refs:
            sid, call_id = ref.segment_id, ref.call_id
            text = texts[sid]
            tokens = count(text)
            if call_id is None or tokens < self._min_tokens:
                proposals.append(Proposal(sid, None, reason="below_min_tokens"))
            elif resume and turns.get(call_id, 0) < self._min_age_turns:
                proposals.append(Proposal(sid, None, reason="too_recent"))
            elif not resume and call_id not in stored:
                proposals.append(Proposal(sid, None, reason="not_resume"))  # PR-023
            else:
                proposals.append(Proposal(sid, STUB.format(tokens=tokens)))
        return proposals

    def decode_request(
        self, texts: Mapping[str, str], refs: Sequence[SegmentRef]
    ) -> dict[str, str]:
        return dict(texts)  # SELECTIVE: nothing to decode
