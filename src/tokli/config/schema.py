"""Configuration schema (SPEC 017). S0 defines only the ``tokens`` section (SPEC 008).

Every setting is addressed as ``<section>.<key>``. A layer that sets a key replaces its whole
value (CF-001).
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

TokenizerName = Literal["o200k_base", "cl100k_base"]

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


class ModelMapEntry(BaseModel):
    """One ordered ``tokens.model_map`` rule: model-name glob → tokenizer."""

    model_config = _STRICT

    pattern: str = Field(min_length=1)
    tokenizer: TokenizerName


DEFAULT_MODEL_MAP: tuple[ModelMapEntry, ...] = (
    ModelMapEntry(pattern="gpt-*", tokenizer="o200k_base"),
    ModelMapEntry(pattern="o*", tokenizer="o200k_base"),
    ModelMapEntry(pattern="claude-*", tokenizer="o200k_base"),
)


class TokensSection(BaseModel):
    model_config = _STRICT

    default: TokenizerName = "o200k_base"
    model_map: tuple[ModelMapEntry, ...] = DEFAULT_MODEL_MAP


class TokliSettings(BaseModel):
    """The validated, immutable settings. Build it only through ``load_config``."""

    model_config = _STRICT

    tokens: TokensSection = Field(default_factory=TokensSection)


# Sections whose values change forwarded behaviour and therefore enter ``config_hash`` (CF-006).
BEHAVIOUR_SECTIONS: tuple[str, ...] = ("tokens",)


@dataclass(frozen=True)
class KeyInfo:
    """Metadata of one schema key.

    ``text`` keys take raw strings from env and --set; all other keys take JSON.
    """

    key: str
    env_var: str
    text: bool


def _is_text(annotation: object) -> bool:
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is Literal:
        return all(isinstance(arg, str) for arg in get_args(annotation))
    if origin in (Union, types.UnionType):
        return False
    return False


def schema_keys() -> dict[str, KeyInfo]:
    """All ``<section>.<key>`` settings, in schema order."""
    keys: dict[str, KeyInfo] = {}
    for section, section_field in TokliSettings.model_fields.items():
        section_model = section_field.annotation
        assert isinstance(section_model, type) and issubclass(section_model, BaseModel)
        for name, field in section_model.model_fields.items():
            key = f"{section}.{name}"
            env_var = f"TOKLI_{section.upper()}__{name.upper()}"
            keys[key] = KeyInfo(key=key, env_var=env_var, text=_is_text(field.annotation))
    return keys
