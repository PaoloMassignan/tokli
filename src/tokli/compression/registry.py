"""The explicit compressor registry (CC-011). Adding a compressor = one module + one entry here."""

from __future__ import annotations

from collections.abc import Sequence

from tokli.compression.contract import AnyCompressor
from tokli.compressors.duplicate_tool_results import DuplicateToolResults
from tokli.compressors.edit_args_on_resume import EditArgsOnResume
from tokli.compressors.json_minify import JsonMinify
from tokli.compressors.log_filter import LogFilter
from tokli.compressors.reread_by_reference import RereadByReference
from tokli.compressors.search_group import SearchGroup


def build_registry(
    *,
    duplicate_min_tokens: int = 64,
    duplicate_require_same_call: bool = False,
    search_group_min_lines: int = 5,
    log_debug_sample: int = 10,
    resume_after_s: float = 3600.0,
    resume_min_age_turns: int = 4,
    resume_min_tokens: int = 64,
    reread_tools: Sequence[str] = ("Read",),
    reread_min_run_lines: int = 5,
    reread_max_lines: int = 20_000,
) -> tuple[AnyCompressor, ...]:
    return (
        JsonMinify(),
        DuplicateToolResults(duplicate_min_tokens, duplicate_require_same_call),
        SearchGroup(search_group_min_lines),
        LogFilter(log_debug_sample),
        EditArgsOnResume(resume_after_s, resume_min_age_turns, resume_min_tokens),
        RereadByReference(reread_tools, reread_min_run_lines, reread_max_lines),
    )


REGISTRY: tuple[AnyCompressor, ...] = build_registry()
