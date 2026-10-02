"""Test helpers shared across test modules."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from tokli.tokens import TokenizerSpec

# Read at import, before any fixture scrubs the environment. Points at a data dir that contains the
# real, provisioned tokenizer files (set in CI after `tokli setup tokenizers`).
PROVISIONED_DATA_DIR = os.environ.get("TEST_TOKLI_PROVISIONED_DATA_DIR")

GOLDEN = Path(__file__).parent / "golden"

FAKE_TOKENIZER_BYTES = b"dG9rbGk= 0\nZmFrZQ== 1\n"
FAKE_SPEC = TokenizerSpec(
    name="o200k_base",
    filename="o200k_base.tiktoken",
    url="https://tokenizers.invalid/o200k_base.tiktoken",
    sha256=hashlib.sha256(FAKE_TOKENIZER_BYTES).hexdigest(),
)
FAKE_CATALOG = {"o200k_base": FAKE_SPEC}


def home_env(home: Path) -> dict[str, str]:
    """Home-related variables for every supported platform, all inside ``home``."""
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
    }


def platform_name() -> str:
    return sys.platform


def read_golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def token_fixture_strings() -> list[str]:
    """200 deterministic strings mixing prose, code, JSON, whitespace and non-ASCII (AC-TM-1)."""
    import random

    rng = random.Random(20260930)
    pieces = [
        "the",
        "quick",
        "brown",
        "fox",
        "def",
        "return",
        "{",
        "}",
        "[",
        "]",
        ":",
        ",",
        '"key"',
        "0.5",
        "1e3",
        "\n",
        "\r\n",
        "\t",
        "    ",
        "café",
        "naïve",
        "漢字",
        "😀",
        "—",
        "<tag>",
        "</tag>",
        "path/to/file.py",
        "C:\\dev\\x",
        "SELECT * FROM t;",
        "x = y + 1",
        "null",
    ]
    out = []
    for i in range(200):
        n = rng.randint(0, 60)
        out.append(
            "".join(rng.choice(pieces) + rng.choice(["", " ", ""]) for _ in range(n)) + str(i)
        )
    return out


class FakeCounter:
    """Deterministic stand-in for a tokenizer: one token per character."""

    tokenizer_id = "fake:chars"

    def count(self, text: str) -> int:
        return len(text)


def make_request(*segments: tuple[str, str], tool_names: tuple[str | None, ...] = ()):  # type: ignore[no-untyped-def]
    """A canonical request with one segment per ``(kind, text)``.

    USER_TEXT and TOOL_RESULT segments are mutable.
    """
    from tokli.domain.models import MUTABLE_ELIGIBLE, CanonicalRequest, Segment, SegmentKind

    built = []
    for i, (kind, text) in enumerate(segments):
        k = SegmentKind(kind)
        name = (
            tool_names[i]
            if i < len(tool_names)
            else ("SomeTool" if k is SegmentKind.TOOL_RESULT else None)
        )
        built.append(
            Segment(
                id=f"s{i}",
                index=i,
                kind=k,
                role="user",
                text=text,
                locator=f"/x/{i}",
                mutable=k in MUTABLE_ELIGIBLE,
                tool_name=name,
            )
        )
    return CanonicalRequest(
        protocol="test",
        provider="test",
        endpoint="/v1/test",
        model="test-model",
        stream=False,
        segments=tuple(built),
        original_json={},
        original_bytes=b"{}",
    )


def view_of(request, spans=None, features=None):  # type: ignore[no-untyped-def]
    from tokli.domain.stage import Features, StageView

    texts = {s.id: s.text for s in request.segments}
    feats = features or {
        s.id: Features(tokens=len(s.text), json_candidate=s.text.strip()[:1] in ("{", "["))
        for s in request.segments
    }
    return StageView(texts=texts, spans=spans or {}, features=feats)
