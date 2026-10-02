"""Supported tokenizers and their pinned data files (TM-010).

The split patterns and special-token ids are copied from tiktoken 0.14.0
(``tiktoken_ext/openai_public.py``, MIT licence, Copyright (c) 2022 OpenAI, Shantanu Jain), so that
Tokli can build the encodings from its own verified files without tiktoken's download cache.

The SHA-256 values were verified on 2026-09-29 against the published files and against the
``expected_hash`` values declared by the tiktoken library (ADR 0001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class TokenizerSpec:
    name: str
    filename: str
    url: str
    sha256: str
    pattern: str = ""
    special_tokens: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def tokenizer_id(self) -> str:
        """Stable identity used in records and diagnostics (TM-001)."""
        return f"tiktoken:{self.name}@{self.sha256[:12]}"


_O200K_PATTERN = "[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]*[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|[^\\r\\n\\p{L}\\p{N}]?[\\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M}]+[\\p{Ll}\\p{Lm}\\p{Lo}\\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?|\\p{N}{1,3}| ?[^\\s\\p{L}\\p{N}]+[\\r\\n/]*|\\s*[\\r\\n]+|\\s+(?!\\S)|\\s+"  # noqa: E501
_CL100K_PATTERN = "'(?i:[sdmt]|ll|ve|re)|[^\\r\\n\\p{L}\\p{N}]?+\\p{L}++|\\p{N}{1,3}+| ?[^\\s\\p{L}\\p{N}]++[\\r\\n]*+|\\s++$|\\s*[\\r\\n]|\\s+(?!\\S)|\\s"  # noqa: E501

_BASE_URL = "https://openaipublic.blob.core.windows.net/encodings/"

CATALOG: Mapping[str, TokenizerSpec] = MappingProxyType(
    {
        "o200k_base": TokenizerSpec(
            name="o200k_base",
            filename="o200k_base.tiktoken",
            url=_BASE_URL + "o200k_base.tiktoken",
            sha256="446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
            pattern=_O200K_PATTERN,
            special_tokens=MappingProxyType({"<|endoftext|>": 199999, "<|endofprompt|>": 200018}),
        ),
        "cl100k_base": TokenizerSpec(
            name="cl100k_base",
            filename="cl100k_base.tiktoken",
            url=_BASE_URL + "cl100k_base.tiktoken",
            sha256="223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
            pattern=_CL100K_PATTERN,
            special_tokens=MappingProxyType(
                {
                    "<|endoftext|>": 100257,
                    "<|fim_prefix|>": 100258,
                    "<|fim_middle|>": 100259,
                    "<|fim_suffix|>": 100260,
                    "<|endofprompt|>": 100276,
                }
            ),
        ),
    }
)


def tokenizer_dir(data_dir: Path) -> Path:
    return data_dir / "tokenizers"
