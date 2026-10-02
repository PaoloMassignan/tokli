"""SPEC 010 `json_minify` (CP-JM-001…005): structural equivalence and byte-exact strings."""

from __future__ import annotations

import json
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tokli.compression.contract import SegmentView
from tokli.compressors.json_minify import JsonMinify
from tokli.domain.models import SegmentKind
from tokli.domain.stage import Features

MINIFY = JsonMinify()
VIEW = SegmentView(
    kind=SegmentKind.TOOL_RESULT, role="user", tool_name="t", is_error=False, protected=()
)


def features(text: str) -> Features:
    return Features(tokens=len(text), json_candidate=text.strip()[:1] in ("{", "["))


def parse_source(text: str) -> object:
    """The declared parser P: pairs kept in order, numbers compared by spelling."""

    def reject(name: str) -> object:
        raise ValueError(name)

    return json.loads(
        text, object_pairs_hook=list, parse_float=str, parse_int=str, parse_constant=reject
    )


WS = st.sampled_from(["", " ", "\n", "\r\n", "\t", "  \n    ", "\r\n\t "])
NUMBERS = st.sampled_from(["0", "-1", "1.0", "1e2", "-3.5E-4", "10.00", "123456789012345678901"])
STRINGS = st.builds(
    lambda s, ascii_only: json.dumps(s, ensure_ascii=ascii_only),
    st.text(max_size=12),
    st.booleans(),
)


def json_text() -> st.SearchStrategy[str]:
    scalars = st.one_of(NUMBERS, STRINGS, st.sampled_from(["true", "false", "null"]))

    def extend(children: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
        arrays = st.builds(
            lambda items, a, b, sep: a + "[" + b + sep.join(items) + a + "]",
            st.lists(children, max_size=4),
            WS,
            WS,
            st.sampled_from([",", ", ", " ,\n  "]),
        )
        members = st.lists(st.tuples(STRINGS, children), max_size=4)
        objects = st.builds(
            lambda pairs, a, b: (
                "{" + a + ("," + b).join(f"{k}{a}:{b}{v}" for k, v in pairs) + b + "}"
            ),
            members,
            WS,
            WS,
        )
        return st.one_of(arrays, objects)

    return st.builds(
        lambda ws1, v, ws2: ws1 + v + ws2, WS, st.recursive(scalars, extend, max_leaves=12), WS
    )


@settings(max_examples=300, deadline=None)
@given(json_text())
def prop_json_minify_decode_roundtrip(text: str) -> None:
    applicable = MINIFY.applicable(text, VIEW, features(text))
    out = MINIFY.compress(text, VIEW) if applicable.ok else None
    result = text if out is None else out
    assert MINIFY.decode(result) == result
    assert parse_source(result) == parse_source(text)
    assert MINIFY.equivalent(text, MINIFY.decode(result))
    if out is not None:
        assert len(out) < len(text)


def test_json_minify_basic() -> None:
    text = '{\n  "name": "tokli",\n  "tags": [\n    "proxy",\n    "a  b"\n  ]\n}\n'
    assert MINIFY.applicable(text, VIEW, features(text)).ok
    assert MINIFY.compress(text, VIEW) == '{"name":"tokli","tags":["proxy","a  b"]}'


def test_json_minify_preserves_number_spelling() -> None:
    text = "[ 1.0, 1e2, -0.50, 10.00, 12345678901234567890123 ]"
    assert MINIFY.compress(text, VIEW) == "[1.0,1e2,-0.50,10.00,12345678901234567890123]"


def test_json_minify_preserves_escapes_and_unicode() -> None:
    text = '{ "a": "caf\\u00e9 \\"q\\" \\\\ \\n", "b": "café" }'
    assert MINIFY.compress(text, VIEW) == '{"a":"caf\\u00e9 \\"q\\" \\\\ \\n","b":"café"}'


def test_json_minify_preserves_duplicate_keys() -> None:
    text = '{ "k": 1,\n  "k": 2 }'
    out = MINIFY.compress(text, VIEW)
    assert out == '{"k":1,"k":2}'
    assert parse_source(out) == [("k", "1"), ("k", "2")]


@pytest.mark.parametrize(
    "text",
    [
        'result: {"a": 1}',
        '{"a": 1} trailing',
        "plain prose, not json at all",
        '{"a": 1',
        "",
    ],
)
def test_json_minify_not_applicable_on_mixed_text(text: str) -> None:
    applicability = MINIFY.applicable(text, VIEW, features(text))
    assert not applicability.ok
    assert applicability.reason == "not_json"


def test_json_minify_not_applicable_without_whitespace() -> None:
    text = '{"a":[1,2]}'
    applicability = MINIFY.applicable(text, VIEW, features(text))
    assert not applicability.ok and applicability.reason == "no_whitespace"


@pytest.mark.parametrize("text", ["[ NaN ]", "[ Infinity ]", '{ "a": -Infinity }'])
def test_json_minify_rejects_nan(text: str) -> None:
    assert not MINIFY.applicable(text, VIEW, features(text)).ok


def test_json_minify_crlf_roundtrip() -> None:
    text = '{\r\n  "a": "x\\r\\ny",\r\n  "b": [\r\n    1,\n    2\r\n  ]\r\n}\r\n'
    out = MINIFY.compress(text, VIEW)
    assert out == '{"a":"x\\r\\ny","b":[1,2]}'
    assert parse_source(out) == parse_source(text)


def test_json_minify_linear_time() -> None:
    # ~1 KB items with one long string each: whitespace both inside and outside strings, few
    # literals per megabyte, so a 50 MB input stays fast while the work remains proportional.
    item = (
        '  {\n    "id": 1,\n    "text": "' + "value with spaces " * 50 + '",\n    "ok": true\n  }'
    )

    def build(megabytes: int) -> str:
        count = megabytes * 1_000_000 // (len(item) + 2)
        return "[\n" + ",\n".join([item] * count) + "\n]"

    # SCR-001: 5 MB and 50 MB are both larger than CPU caches, so the ratio reflects the algorithm.
    small, large = build(5), build(50)

    def elapsed(text: str) -> float:
        best = float("inf")
        for _ in range(3):  # best of three: robust against scheduler noise on shared CI runners
            start = time.perf_counter()
            MINIFY.compress(text, VIEW)
            best = min(best, time.perf_counter() - start)
        return best

    elapsed(small)  # warm-up
    ratio = elapsed(large) / max(elapsed(small), 1e-6)
    assert ratio <= 15, ratio
