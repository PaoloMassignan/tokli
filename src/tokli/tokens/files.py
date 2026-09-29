"""Tokenizer file verification (TM-006, TM-010). Reads files only when asked, never at import."""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass
from pathlib import Path

from tokli.tokens.catalog import TokenizerSpec, tokenizer_dir


class TokenizerState(enum.Enum):
    PRESENT = "present"
    MISSING = "missing"
    HASH_MISMATCH = "hash mismatch"


@dataclass(frozen=True)
class TokenizerStatus:
    spec: TokenizerSpec
    path: Path
    state: TokenizerState


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_tokenizer(spec: TokenizerSpec, data_dir: Path) -> TokenizerStatus:
    path = tokenizer_dir(data_dir) / spec.filename
    if not path.is_file():
        return TokenizerStatus(spec, path, TokenizerState.MISSING)
    state = (
        TokenizerState.PRESENT
        if sha256_hex(path.read_bytes()) == spec.sha256
        else TokenizerState.HASH_MISMATCH
    )
    return TokenizerStatus(spec, path, state)
