"""The explicit compressor registry (CC-011). Adding a compressor = one module + one entry here."""

from __future__ import annotations

from tokli.compression.contract import AnyCompressor
from tokli.compressors.duplicate_tool_results import DuplicateToolResults
from tokli.compressors.json_minify import JsonMinify
from tokli.compressors.log_filter import LogFilter
from tokli.compressors.search_group import SearchGroup


def build_registry(
    *,
    duplicate_min_tokens: int = 64,
    duplicate_require_same_call: bool = False,
    search_group_min_lines: int = 5,
    log_debug_sample: int = 10,
) -> tuple[AnyCompressor, ...]:
    return (
        JsonMinify(),
        DuplicateToolResults(duplicate_min_tokens, duplicate_require_same_call),
        SearchGroup(search_group_min_lines),
        LogFilter(log_debug_sample),
    )


REGISTRY: tuple[AnyCompressor, ...] = build_registry()
