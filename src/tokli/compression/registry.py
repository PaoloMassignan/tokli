"""The explicit compressor registry (CC-011). Adding a compressor = one module + one entry here."""

from __future__ import annotations

from tokli.compression.contract import AnyCompressor
from tokli.compressors.duplicate_tool_results import DuplicateToolResults
from tokli.compressors.json_minify import JsonMinify


def build_registry(
    *, duplicate_min_tokens: int = 64, duplicate_require_same_call: bool = False
) -> tuple[AnyCompressor, ...]:
    return (JsonMinify(), DuplicateToolResults(duplicate_min_tokens, duplicate_require_same_call))


REGISTRY: tuple[AnyCompressor, ...] = build_registry()
