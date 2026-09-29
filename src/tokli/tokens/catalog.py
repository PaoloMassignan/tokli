"""Supported tokenizers and their pinned data files (TM-010).

The SHA-256 values were verified on 2026-09-29 against the published files and against the
``expected_hash`` values declared by the tiktoken library (ADR 0001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class TokenizerSpec:
    name: str
    filename: str
    url: str
    sha256: str

    @property
    def tokenizer_id(self) -> str:
        """Stable identity used in records and diagnostics (TM-001)."""
        return f"tiktoken:{self.name}@{self.sha256[:12]}"


_BASE_URL = "https://openaipublic.blob.core.windows.net/encodings/"

CATALOG: Mapping[str, TokenizerSpec] = MappingProxyType(
    {
        "o200k_base": TokenizerSpec(
            name="o200k_base",
            filename="o200k_base.tiktoken",
            url=_BASE_URL + "o200k_base.tiktoken",
            sha256="446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
        ),
        "cl100k_base": TokenizerSpec(
            name="cl100k_base",
            filename="cl100k_base.tiktoken",
            url=_BASE_URL + "cl100k_base.tiktoken",
            sha256="223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
        ),
    }
)


def tokenizer_dir(data_dir: Path) -> Path:
    return data_dir / "tokenizers"
