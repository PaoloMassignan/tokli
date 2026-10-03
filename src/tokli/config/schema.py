"""Configuration schema (SPEC 017; keys added in S1 per its "Keys added in S1" table).

Every setting is a leaf addressed by its dotted path, e.g. ``compressors.json_minify.enabled``.
A layer that sets a key replaces its whole value (CF-001).
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

TokenizerName = Literal["o200k_base", "cl100k_base"]
SegmentKindName = Literal[
    "SYSTEM",
    "TOOL_DESCRIPTION",
    "USER_TEXT",
    "ASSISTANT_TEXT",
    "TOOL_CALL_ARGS",
    "TOOL_RESULT",
    "OTHER_TEXT",
]

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


class ServerSection(BaseModel):
    model_config = _STRICT

    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=0, le=65535)
    allow_remote: bool = False


class UpstreamSettings(BaseModel):
    model_config = _STRICT

    base_url: str = Field(min_length=1)
    connect_timeout_s: float = Field(default=10.0, gt=0)
    read_timeout_s: float = Field(default=600.0, gt=0)


class UpstreamsSection(BaseModel):
    model_config = _STRICT

    anthropic: UpstreamSettings = UpstreamSettings(base_url="https://api.anthropic.com")


class TlsSection(BaseModel):
    model_config = _STRICT

    ca_bundle: str | None = None


class LimitsSection(BaseModel):
    model_config = _STRICT

    max_transform_bytes: int = Field(default=32 * 1024 * 1024, gt=0)
    usage_parser_buffer: int = Field(default=1024 * 1024, gt=0)  # AN-009


class CompressionSection(BaseModel):
    model_config = _STRICT

    segment_kinds: tuple[SegmentKindName, ...] = ("TOOL_RESULT", "USER_TEXT")
    verbatim_tools: tuple[str, ...] = ("Read", "Bash", "shell", "shell_command", "container.exec")
    min_segment_tokens: int = Field(default=64, ge=0)
    min_gain_tokens: int = Field(default=4, ge=0)
    min_gain_ratio: float = Field(default=0.01, ge=0, le=1)
    request_budget_ms: float = Field(default=50.0, gt=0)
    per_call_timeout_ms: float = Field(default=200.0, gt=0)
    verify_lossless: bool = False
    result_cache_mb: int = Field(default=64, ge=0)  # CC-024; 0 = off


class CompressorToggle(BaseModel):
    model_config = _STRICT

    enabled: bool


class CompressorsSection(BaseModel):
    model_config = _STRICT

    json_minify: CompressorToggle = CompressorToggle(enabled=True)


class ObservabilitySection(BaseModel):
    model_config = _STRICT

    trace_buffer: int = Field(default=500, ge=1)
    response_header: bool = True
    log_format: Literal["json", "text"] = "json"
    log_file: bool = False  # OB-013


class TelemetrySection(BaseModel):
    model_config = _STRICT

    retention_days: int = Field(default=30, ge=0)


class TokliSettings(BaseModel):
    """The validated, immutable settings. Build it only through ``load_config``."""

    model_config = _STRICT

    server: ServerSection = Field(default_factory=ServerSection)
    upstreams: UpstreamsSection = Field(default_factory=UpstreamsSection)
    tls: TlsSection = Field(default_factory=TlsSection)
    limits: LimitsSection = Field(default_factory=LimitsSection)
    compression: CompressionSection = Field(default_factory=CompressionSection)
    compressors: CompressorsSection = Field(default_factory=CompressorsSection)
    tokens: TokensSection = Field(default_factory=TokensSection)
    observability: ObservabilitySection = Field(default_factory=ObservabilitySection)
    telemetry: TelemetrySection = Field(default_factory=TelemetrySection)


# Sections whose values change forwarded behaviour and therefore enter ``config_hash`` (CF-006).
BEHAVIOUR_SECTIONS: tuple[str, ...] = ("compression", "compressors", "limits", "tokens")


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
        args = [a for a in get_args(annotation) if a is not type(None)]
        return len(args) == 1 and _is_text(args[0])
    return False


def _is_model(annotation: object) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _walk(model: type[BaseModel], prefix: tuple[str, ...], keys: dict[str, KeyInfo]) -> None:
    for name, field in model.model_fields.items():
        path = (*prefix, name)
        if _is_model(field.annotation):
            assert field.annotation is not None
            _walk(field.annotation, path, keys)
            continue
        key = ".".join(path)
        env_var = "TOKLI_" + "__".join(part.upper() for part in path)
        keys[key] = KeyInfo(key=key, env_var=env_var, text=_is_text(field.annotation))


def schema_keys() -> dict[str, KeyInfo]:
    """All leaf settings, in schema order."""
    keys: dict[str, KeyInfo] = {}
    _walk(TokliSettings, (), keys)
    return keys


def is_section(path: tuple[str, ...]) -> bool:
    """True when ``path`` names a nested model (not a leaf) of the schema."""
    model: type[BaseModel] = TokliSettings
    for part in path:
        field = model.model_fields.get(part)
        if field is None or not _is_model(field.annotation):
            return False
        model = field.annotation  # type: ignore[assignment]
    return True
