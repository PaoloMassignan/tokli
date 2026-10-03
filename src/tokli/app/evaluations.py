"""Evaluation status of compressors for the UI (UI-003, QE-016; ADR 0009).

The wheel carries a copy of ``evals/records/`` as ``tokli/_eval_records/``; a development
checkout reads the repository folder. A record for another version of the compressor is
``outdated``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import tokli
from tokli.compression.contract import CompressorSpec


def records_dir() -> Path | None:
    package = Path(tokli.__file__).resolve().parent
    for candidate in (package / "_eval_records", package.parents[1] / "evals" / "records"):
        if candidate.is_dir():
            return candidate
    return None


def evaluation_status(spec: CompressorSpec, folder: Path | None) -> dict[str, Any]:
    path = folder / f"{spec.id}.yaml" if folder is not None else None
    if path is None or not path.is_file():
        return {"status": "none"}
    try:
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {"status": "none"}
    if not isinstance(record, dict):
        return {"status": "none"}
    return {
        "status": "current" if str(record.get("version")) == spec.version else "outdated",
        "tier": record.get("tier"),
        "verdict": record.get("verdict"),
        "model": record.get("model"),
        "date": str(record.get("date")) if record.get("date") is not None else None,
    }
