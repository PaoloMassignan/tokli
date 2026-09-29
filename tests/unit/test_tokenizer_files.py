"""TM-006, TM-010: tokenizer file states and the pinned catalog."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tests.helpers import FAKE_SPEC, FAKE_TOKENIZER_BYTES
from tokli.tokens import CATALOG, TokenizerState, check_tokenizer, sha256_hex, tokenizer_dir


def test_sha256_hex_matches_hashlib() -> None:
    assert sha256_hex(b"tokli") == hashlib.sha256(b"tokli").hexdigest()


def test_check_tokenizer_states(tmp_path: Path) -> None:
    status = check_tokenizer(FAKE_SPEC, tmp_path)
    assert status.state is TokenizerState.MISSING
    assert status.path == tokenizer_dir(tmp_path) / FAKE_SPEC.filename

    status.path.parent.mkdir(parents=True)
    status.path.write_bytes(FAKE_TOKENIZER_BYTES)
    assert check_tokenizer(FAKE_SPEC, tmp_path).state is TokenizerState.PRESENT

    status.path.write_bytes(FAKE_TOKENIZER_BYTES + b"x")
    assert check_tokenizer(FAKE_SPEC, tmp_path).state is TokenizerState.HASH_MISMATCH


def test_catalog_entries_are_pinned() -> None:
    assert set(CATALOG) == {"o200k_base", "cl100k_base"}
    for name, spec in CATALOG.items():
        assert spec.name == name
        assert re.fullmatch(r"[0-9a-f]{64}", spec.sha256)
        assert spec.filename == f"{name}.tiktoken"
        assert spec.url == f"https://openaipublic.blob.core.windows.net/encodings/{spec.filename}"
        assert spec.tokenizer_id == f"tiktoken:{name}@{spec.sha256[:12]}"
