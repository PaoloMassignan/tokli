"""``json_minify``: remove insignificant whitespace from a segment that is solely strict JSON
(SPEC 010, CP-JM-001…005). LOSSLESS, structural equivalence; ``decode`` is the identity."""

from __future__ import annotations

import json
import re

from tokli.compression.contract import Applicability, CompressorSpec, SegmentView
from tokli.domain.models import SegmentKind
from tokli.domain.stage import Features

SPEC = CompressorSpec(
    id="json_minify",
    name="JSON minify",
    version="1",
    kind="LOSSLESS",
    equivalence="structural",
    scope="segment",
    prefix_stable=True,
    guarantees=(
        "structural equality under the source-spelling JSON parser "
        "(prop_json_minify_decode_roundtrip)",
        "linear time and memory (test_json_minify_linear_time)",
    ),
    assumptions=("reads_minified_json", "not_quoted_verbatim"),
    stage="normalize",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT}),
    min_tokens=0,
    cost_class="cheap",
    terminal=False,
    requires=(),
    default_enabled=True,
)


_JSON_WS_CHARS = " \t\n\r"
_JSON_WS = frozenset(_JSON_WS_CHARS)


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-standard JSON constant {name}")


def _parse_source(text: str) -> object:
    """The declared parser P: key order and duplicates kept, numbers compared by spelling."""
    return json.loads(
        text,
        object_pairs_hook=list,
        parse_float=str,
        parse_int=str,
        parse_constant=_reject_constant,
    )


# One capturing group. "Unrolled loop" form: runs of ordinary characters are consumed in one step,
# which is several times faster than an alternation per character on large inputs.
_STRING_LITERAL = re.compile(r'("[^"\\]*(?:\\.[^"\\]*)*")', re.DOTALL)
_DROP_WS = str.maketrans("", "", _JSON_WS_CHARS)


def _minify(text: str) -> tuple[str, bool]:
    """Drop JSON whitespace outside string literals. Returns the text and whether anything went.

    Only called on text that parses as strict JSON, so every ``"`` outside a literal starts one.
    String literals are copied verbatim; the gaps between them lose their whitespace.
    """
    parts = _STRING_LITERAL.split(text)  # even indices: between literals; odd: the literals
    parts[0::2] = [gap.translate(_DROP_WS) for gap in parts[0::2]]
    minified = "".join(parts)
    return minified, len(minified) != len(text)


class JsonMinify:
    spec = SPEC

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        stripped = text.strip(_JSON_WS_CHARS)
        if not stripped or stripped[0] not in "{[":
            return Applicability(False, "not_json")
        try:
            _parse_source(stripped)
        except ValueError:  # includes json.JSONDecodeError
            return Applicability(False, "not_json")
        if not _minify(text)[1]:
            return Applicability(False, "no_whitespace")
        return Applicability(True)

    def compress(self, text: str, view: SegmentView) -> str | None:
        minified, removed = _minify(text)
        return minified if removed else None

    def decode(self, text: str) -> str:
        return text

    def equivalent(self, original: str, decoded: str) -> bool:
        try:
            return _parse_source(original) == _parse_source(decoded)
        except ValueError:
            return False
