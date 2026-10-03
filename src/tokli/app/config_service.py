"""`GET`/`PATCH /tokli/api/config` use cases (SPEC 015 API-005, API-007; SPEC 017 CF-002,
CF-009; ADR 0009). Only UI-editable keys change, never a key that env or the CLI pins."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from typing import Any

import yaml

from tokli.app.runtime import Runtime
from tokli.config import ConfigError, EffectiveConfig, schema_keys
from tokli.config.loader import read_ui_overrides, ui_document, validate_values

API_VERSION = 1
_LOG = logging.getLogger("tokli.config")
# One PATCH at a time, from reading the overrides to the swap: two concurrent PATCHes must not
# both merge into the same old file (API-007, S4.5 D1).
_APPLY_LOCK = threading.Lock()


class PatchError(Exception):
    """A refused change: HTTP status and the error body."""

    def __init__(self, status: int, error: dict[str, Any]) -> None:
        super().__init__(error.get("type", "error"))
        self.status = status
        self.error = error


def config_view(config: EffectiveConfig) -> dict[str, Any]:
    """Every key with its value, source, editability and lock (CF-002). No secrets exist in the
    schema (CF-010)."""
    keys = schema_keys()
    dumped = config.settings.model_dump(mode="json")
    settings = []
    for key, info in keys.items():
        node: Any = dumped
        for part in key.split("."):
            node = node[part]
        settings.append(
            {
                "key": key,
                "value": node,
                "source": config.sources[key],
                "ui_editable": info.ui_editable,
                "locked_by": config.locked.get(key),
            }
        )
    return {"api_version": API_VERSION, "config_hash": config.config_hash, "settings": settings}


def apply_patch(runtime: Runtime, changes: Mapping[str, object]) -> dict[str, Any]:
    """Validates, persists and applies a change; returns the new view (API-007)."""
    with _APPLY_LOCK:
        return _apply(runtime, changes)


def _apply(runtime: Runtime, changes: Mapping[str, object]) -> dict[str, Any]:
    config = runtime.current().config
    keys = schema_keys()
    fields: dict[str, str] = {}
    for key in changes:
        if key not in keys:
            fields[key] = "unknown setting"
        elif not keys[key].ui_editable:
            fields[key] = "cannot be changed from the UI"
    if fields:
        raise PatchError(400, {"type": "invalid_parameter", "fields": fields})
    for key in changes:
        if key in config.locked:
            raise PatchError(409, {"type": "locked", "key": key, "source": config.locked[key]})
    fields = validate_values(changes)
    if fields:
        raise PatchError(400, {"type": "invalid_parameter", "fields": fields})
    path = config.ui_overrides_path
    try:
        current = read_ui_overrides(path)
    except ConfigError as exc:
        raise PatchError(500, {"type": "overrides_unreadable", "message": exc.cause}) from exc
    proposed = {**current, **changes}
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            yaml.safe_dump(ui_document(proposed), sort_keys=True), encoding="utf-8", newline="\n"
        )
        os.replace(tmp, path)  # atomic: the old file stays if this fails
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise PatchError(500, {"type": "write_failed", "message": type(exc).__name__}) from exc
    new = runtime.swap(config.reload())
    _LOG.info(
        "configuration changed",
        extra={
            "tokli": {
                "event": "config_change",
                "keys": sorted(changes),
                "config_hash": new.config.config_hash,
            }
        },
    )
    return config_view(new.config)
