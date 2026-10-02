"""TM-001, TM-002, TM-006, TM-008: counters built from verified files, selection by model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import (
    FAKE_SPEC,
    FAKE_TOKENIZER_BYTES,
    GOLDEN,
    PROVISIONED_DATA_DIR,
    token_fixture_strings,
)
from tokli.tokens import CATALOG, tokenizer_dir
from tokli.tokens.counter import TokenizerSelector, TokenizerUnavailableError, load_counter

needs_real_tokenizers = pytest.mark.skipif(
    PROVISIONED_DATA_DIR is None, reason="set TEST_TOKLI_PROVISIONED_DATA_DIR"
)


def provisioned(name: str) -> Path:
    assert PROVISIONED_DATA_DIR is not None
    data_dir = Path(PROVISIONED_DATA_DIR)
    if not (tokenizer_dir(data_dir) / CATALOG[name].filename).is_file():
        pytest.skip(f"{name} not provisioned")
    return data_dir


@needs_real_tokenizers
@pytest.mark.parametrize("name", ["o200k_base", "cl100k_base"])
def test_token_counts_match_reference_values(name: str) -> None:
    reference = json.loads((GOLDEN / "token_reference_counts.json").read_text(encoding="utf-8"))
    counter = load_counter(CATALOG[name], provisioned(name))
    assert [counter.count(s) for s in reference["samples"]] == reference["counts"][name]
    assert counter.tokenizer_id == CATALOG[name].tokenizer_id


@needs_real_tokenizers
@pytest.mark.parametrize("name", ["o200k_base", "cl100k_base"])
def test_token_counts_stable_fixture(name: str) -> None:
    golden = json.loads((GOLDEN / "token_counts_200.json").read_text(encoding="utf-8"))
    counter = load_counter(CATALOG[name], provisioned(name))
    assert [counter.count(s) for s in token_fixture_strings()] == golden["counts"][name]


def test_load_counter_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TokenizerUnavailableError) as info:
        load_counter(FAKE_SPEC, tmp_path)
    assert info.value.path == tokenizer_dir(tmp_path) / FAKE_SPEC.filename
    assert "missing" in str(info.value)


def test_load_counter_refuses_tampered_file(tmp_path: Path) -> None:
    target = tokenizer_dir(tmp_path) / FAKE_SPEC.filename
    target.parent.mkdir(parents=True)
    target.write_bytes(FAKE_TOKENIZER_BYTES + b"x")
    with pytest.raises(TokenizerUnavailableError) as info:
        load_counter(FAKE_SPEC, tmp_path)
    assert "hash mismatch" in str(info.value)


class Named:
    def __init__(self, tokenizer_id: str) -> None:
        self.tokenizer_id = tokenizer_id

    def count(self, text: str) -> int:
        return 0


def test_tokenizer_selected_by_model_map() -> None:
    counters = {"o200k_base": Named("o"), "cl100k_base": Named("c")}
    selector = TokenizerSelector(
        counters,  # type: ignore[arg-type]
        default="o200k_base",
        model_map=[("claude-3-*", "cl100k_base"), ("claude-*", "o200k_base")],
    )
    assert selector.select("claude-3-opus").tokenizer_id == "c"  # first matching rule wins
    assert selector.select("claude-sonnet-4").tokenizer_id == "o"
    assert selector.select("Claude-3-opus").tokenizer_id == "o"  # case-sensitive globs
    assert selector.select("mystery-model").tokenizer_id == "o"  # tokens.default
    assert selector.select(None).tokenizer_id == "o"
