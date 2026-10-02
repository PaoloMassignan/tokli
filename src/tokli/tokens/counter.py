"""Token counting from verified local tokenizer files (TM-001, TM-002, TM-007, TM-008).

Encodings are built from the file that ``tokli setup tokenizers`` verified, with the pinned split
pattern. Nothing is downloaded and nothing is cached outside the data dir.
"""

from __future__ import annotations

import base64
import fnmatch
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from pathlib import Path

import tiktoken

from tokli.tokens.catalog import TokenizerSpec, tokenizer_dir
from tokli.tokens.files import sha256_hex

_CACHE_SIZE = 8192


class TokenizerUnavailableError(Exception):
    def __init__(self, spec: TokenizerSpec, path: Path, problem: str) -> None:
        super().__init__(f"tokenizer {spec.name} {problem}: expected {path}")
        self.spec = spec
        self.path = path


class TokenCounter:
    """Counts tokens of plain text with one tokenizer. Results are cached per text.

    Special-token strings in the text are counted as ordinary text (``encode_ordinary``).
    """

    def __init__(self, spec: TokenizerSpec, mergeable_ranks: Mapping[bytes, int]) -> None:
        self._spec = spec
        self._encoding = tiktoken.Encoding(
            name=spec.name,
            pat_str=spec.pattern,
            mergeable_ranks=dict(mergeable_ranks),
            special_tokens=dict(spec.special_tokens),
        )
        self._cache: OrderedDict[str, int] = OrderedDict()

    @property
    def tokenizer_id(self) -> str:
        return self._spec.tokenizer_id

    def count(self, text: str) -> int:
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)
            return cached
        value = len(self._encoding.encode_ordinary(text))
        self._cache[text] = value
        if len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)
        return value


def _parse_ranks(data: bytes) -> dict[bytes, int]:
    ranks: dict[bytes, int] = {}
    for line in data.splitlines():
        if line:
            token, rank = line.split()
            ranks[base64.b64decode(token)] = int(rank)
    return ranks


def load_counter(spec: TokenizerSpec, data_dir: Path) -> TokenCounter:
    path = tokenizer_dir(data_dir) / spec.filename
    if not path.is_file():
        raise TokenizerUnavailableError(spec, path, "missing")
    data = path.read_bytes()
    if sha256_hex(data) != spec.sha256:
        raise TokenizerUnavailableError(spec, path, "hash mismatch")
    return TokenCounter(spec, _parse_ranks(data))


class TokenizerSelector:
    """Selects the counter for a model name (``tokens.model_map`` globs, then ``tokens.default``).

    Globs are matched case-sensitively; the first matching rule wins.
    """

    def __init__(
        self,
        counters: Mapping[str, TokenCounter],
        default: str,
        model_map: Sequence[tuple[str, str]],
    ) -> None:
        self._counters = dict(counters)
        self._default = default
        self._rules = tuple(model_map)

    def select(self, model: str | None) -> TokenCounter:
        if model is not None:
            for pattern, name in self._rules:
                if fnmatch.fnmatchcase(model, pattern):
                    return self._counters[name]
        return self._counters[self._default]
