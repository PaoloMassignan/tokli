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
