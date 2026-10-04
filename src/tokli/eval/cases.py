"""Case files (QE-013): one YAML file per case under ``<cases dir>/<family>/``."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tokli.eval.checkers import CHECKERS, TOOL_CHECKERS

REQUIRED = ("case_set", "family", "assumption", "checker", "request", "expected")
# Synthetic cases only: no developer paths, no credential-shaped strings (AC-QE-6). The text is
# scanned as JSON, where a backslash is written twice.
_FORBIDDEN = re.compile(
    r"[A-Za-z]:(?:\\\\)+Users(?:\\\\)+|/home/[A-Za-z]|/Users/[A-Za-z]|\bsk-[A-Za-z0-9]|\bBearer\s"
)


@dataclass(frozen=True)
class Case:
    case_id: str
    case_set: str
    family: str
    assumption: str
    checker: str
    request: dict[str, Any]
    expected: str
    expected_read_path: str | None = None  # `answer_or_read` (S8c)


def lint_case(data: Any, source: str) -> list[str]:
    if not isinstance(data, dict):
        return [f"{source}: not a mapping"]
    errors = [f"{source}: missing field '{name}'" for name in REQUIRED if name not in data]
    if data.get("checker") is not None and data.get("checker") not in {**CHECKERS, **TOOL_CHECKERS}:
        errors.append(f"{source}: unknown checker '{data.get('checker')}'")
    if "expected" in data and not isinstance(data["expected"], str):
        errors.append(f"{source}: 'expected' must be a string")
    if data.get("checker") in TOOL_CHECKERS and not isinstance(data.get("expected_read_path"), str):
        errors.append(f"{source}: 'expected_read_path' is required by '{data.get('checker')}'")
    request = data.get("request")
    if "request" in data:
        if not isinstance(request, dict) or not isinstance(request.get("messages"), list):
            errors.append(f"{source}: 'request' must be a Messages body")
        elif "model" in request:
            errors.append(f"{source}: 'request' must not name a model (it comes from --model)")
    if _FORBIDDEN.search(json.dumps(data, ensure_ascii=False)):
        errors.append(f"{source}: forbidden content (developer path or credential pattern)")
    return errors


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*/*.yaml") if p.is_file())


def lint_tree(root: Path) -> list[str]:
    errors: list[str] = []
    for path in _files(root):
        source = path.relative_to(root).as_posix()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{source}: not YAML ({exc.__class__.__name__})")
            continue
        errors.extend(lint_case(data, source))
        if isinstance(data, dict) and data.get("family") != path.parent.name:
            errors.append(f"{source}: family does not match its folder")
    return errors


def load_cases(root: Path, assumptions: Iterable[str]) -> list[Case]:
    """Every case whose family tests one of ``assumptions`` (QE-012). Lint errors are fatal."""
    problems = lint_tree(root)
    if problems:
        raise ValueError("invalid case files: " + "; ".join(problems))
    wanted = set(assumptions)
    cases = []
    for path in _files(root):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["assumption"] not in wanted:
            continue
        cases.append(
            Case(
                case_id=f"{data['family']}/{path.stem}",
                case_set=str(data["case_set"]),
                family=data["family"],
                assumption=data["assumption"],
                checker=data["checker"],
                request=data["request"],
                expected=data["expected"],
                expected_read_path=data.get("expected_read_path"),
            )
        )
    return cases
