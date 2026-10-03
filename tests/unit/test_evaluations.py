"""UI-003 evaluation status (S4, P5; ADR 0009)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from tokli.app.evaluations import evaluation_status, records_dir
from tokli.compressors.json_minify import SPEC


def write(folder: Path, version: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "json_minify.yaml").write_text(
        "compressor: json_minify\n"
        f"version: '{version}'\n"
        "tier: smoke\n"
        "assumptions_covered: [reads_minified_json, not_quoted_verbatim]\n"
        "verdict: no_measurable_damage\n"
        "model: claude-test\n"
        "date: '2026-10-03'\n"
        "report: results/x/report.md\n",
        encoding="utf-8",
    )


def test_records_found_in_a_development_checkout() -> None:
    folder = records_dir()
    assert folder is not None and (folder / "json_minify.yaml").is_file()


def test_current_record(tmp_path: Path) -> None:
    write(tmp_path, SPEC.version)
    assert evaluation_status(SPEC, tmp_path) == {
        "status": "current",
        "tier": "smoke",
        "verdict": "no_measurable_damage",
        "model": "claude-test",
        "date": "2026-10-03",
    }


def test_outdated_record_shown_as_outdated(tmp_path: Path) -> None:
    write(tmp_path, "0")
    assert evaluation_status(SPEC, tmp_path)["status"] == "outdated"


def test_missing_record(tmp_path: Path) -> None:
    other = dataclasses.replace(SPEC, id="never_evaluated")
    assert evaluation_status(other, tmp_path) == {"status": "none"}
    assert evaluation_status(SPEC, None) == {"status": "none"}
