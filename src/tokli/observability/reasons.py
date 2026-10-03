"""The closed set of decision reason codes (TOKLI_OBSERVABILITY §4, OB-004).

Codes with a parameter are written ``name(<value>)``; the set lists the name only.
"""

from __future__ import annotations

ROUTE = frozenset({"known_endpoint", "verbatim_path", "unknown_prefix"})
PASSTHROUGH = frozenset(
    {
        "policy_off",
        "no_mutable_segments",
        "no_applicable_compressor",
        "no_gain",
        "parse_error",
        "content_encoding",
        "too_large",
        "render_error",
        "pipeline_error",
    }
)
SKIP = frozenset(
    {
        "disabled",
        "policy_forbids",
        "unavailable",
        "kind_not_supported",
        "too_small",
        "verbatim_tool",
        "not_applicable",
        "after_terminal",
        "budget_exhausted",
    }
)
REJECT = frozenset(
    {
        "no_gain",
        "below_min_gain",
        "protected_span_changed",
        "reference_target_modified",
        "exception",
        "timeout",
        "decode_mismatch",
    }
)
STAGE = frozenset({"stage_exception", "stage_timeout", "analyzer_returned_patches"})
UPSTREAM = frozenset(
    {"upstream_status", "upstream_unreachable", "upstream_timeout", "client_disconnected"}
)
USAGE = frozenset({"usage_unavailable"})  # (<why>), AN-007
USAGE_WHY = frozenset(
    {
        "upstream_status",
        "content_encoding",
        "buffer_limit",
        "parse_error",
        "no_usage",
        "client_disconnected",
    }
)
CALIBRATION = frozenset({"calibration_outlier", "calibration_unavailable"})  # TM-009

ALL = ROUTE | PASSTHROUGH | SKIP | REJECT | STAGE | UPSTREAM | USAGE | CALIBRATION


def is_known(code: str) -> bool:
    """True when ``code`` (with or without a ``(parameter)``) belongs to the closed set."""
    name, _, rest = code.partition("(")
    if rest and not rest.endswith(")"):
        return False
    return name in ALL
