"""The explicit compressor registry (CC-011). Adding a compressor = one module + one entry here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tokli.compression.contract import AnyCompressor
from tokli.compressors.duplicate_tool_results import DuplicateToolResults
from tokli.compressors.edit_args_on_resume import EditArgsOnResume
from tokli.compressors.json_minify import JsonMinify
from tokli.compressors.log_filter import LogFilter
from tokli.compressors.outline_first_read import DEFAULT_RULES, DEFAULT_TOOLS, OutlineFirstRead
from tokli.compressors.reread_by_reference import RereadByReference
from tokli.compressors.search_group import SearchGroup


def build_registry(
    *,
    duplicate_min_tokens: int = 64,
    duplicate_require_same_call: bool = False,
    search_group_min_lines: int = 5,
    log_debug_sample: int = 10,
    resume_min_age_turns: int = 4,
    resume_min_tokens: int = 64,
    reread_tools: Sequence[str] = ("Read",),
    reread_min_run_lines: int = 5,
    reread_max_lines: int = 20_000,
    outline_tools: Sequence[str] = DEFAULT_TOOLS,
    outline_rules: Mapping[str, str] = DEFAULT_RULES,
    outline_min_tokens: int = 500,
    outline_min_run_lines: int = 3,
) -> tuple[AnyCompressor, ...]:
    compressors: tuple[AnyCompressor, ...] = (
        JsonMinify(),
        OutlineFirstRead(outline_tools, outline_rules, outline_min_tokens, outline_min_run_lines),
        DuplicateToolResults(duplicate_min_tokens, duplicate_require_same_call),
        SearchGroup(search_group_min_lines),
        LogFilter(log_debug_sample),
        EditArgsOnResume(resume_min_age_turns, resume_min_tokens),
        RereadByReference(reread_tools, reread_min_run_lines, reread_max_lines),
    )
    validate_registry(compressors)
    return compressors


def validate_registry(compressors: Sequence[AnyCompressor]) -> None:
    """Registry contract checks: `target_tools` only on a SELECTIVE compressor that is off by
    default (CC-021 (c), S8j SCR-001)."""
    for compressor in compressors:
        spec = compressor.spec
        if spec.target_tools and (spec.kind != "SELECTIVE" or spec.default_enabled):
            raise ValueError(
                f"{spec.id}: target_tools needs a SELECTIVE compressor that is off by default"
            )


REGISTRY: tuple[AnyCompressor, ...] = build_registry()
