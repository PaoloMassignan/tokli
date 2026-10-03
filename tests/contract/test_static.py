"""Static contracts: dependency rules (ARCH §5), MD-04, MD-08, PT-010, PT-011 (S0 rows), MD-19."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "tokli"
TESTS = ROOT / "tests"


def python_sources(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def test_import_contracts() -> None:
    scripts = Path(sysconfig.get_path("scripts"))
    script = scripts / ("lint-imports.exe" if os.name == "nt" else "lint-imports")
    done = subprocess.run([str(script)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_no_dotenv_loading() -> None:
    for path in python_sources(SRC):
        assert "dotenv" not in path.read_text(encoding="utf-8"), path


def test_no_module_reads_cwd_relative_paths() -> None:
    forbidden = re.compile(r"os\.getcwd\(|Path\.cwd\(|Path\(\s*['\"]\.?['\"]\s*\)|os\.curdir")
    for path in python_sources(SRC):
        assert not forbidden.search(path.read_text(encoding="utf-8")), path


def test_fixtures_contain_no_developer_paths() -> None:
    users = "Us" + "ers"
    developer_path = re.compile(
        r"[A-Za-z]:\\\\?"
        + users
        + r"\\\\?(?!dev\b)[A-Za-z]|/"
        + users
        + r"/(?!dev/)[a-z]|/home/(?!dev/)[a-z]"
    )
    for path in TESTS.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".txt", ".yaml", ".json"}:
            text = path.read_text(encoding="utf-8")
            assert not developer_path.search(text), path


S0_CHECKLIST_ROWS = (
    "MD-02",
    "MD-04",
    "MD-05",
    "MD-07",
    "MD-08",
    "MD-16",
    "MD-18",
    "MD-19",
    "MD-20",
    "MD-27",
)


def test_machine_dependence_checklist_tests_exist() -> None:
    spec = (ROOT / "specs" / "018-portability-and-diagnostics" / "spec.md").read_text(
        encoding="utf-8"
    )
    all_tests = "\n".join(p.read_text(encoding="utf-8") for p in python_sources(TESTS))
    for row in S0_CHECKLIST_ROWS:
        line = next(line for line in spec.splitlines() if line.startswith(f"| {row} |"))
        for name in re.findall(r"`(test_[a-z0-9_]+)`", line):
            if "<" in name:
                continue
            assert f"def {name}(" in all_tests, f"{row}: {name}"


@pytest.mark.packaging
@pytest.mark.skipif(
    os.environ.get("RUN_PACKAGING_TESTS") != "1", reason="set RUN_PACKAGING_TESTS=1"
)
def test_wheel_imports_tokli_in_clean_venv(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(tmp_path / "dist"),
            str(ROOT),
        ],
        check=True,
        capture_output=True,
    )
    wheel = next((tmp_path / "dist").glob("tokli-*.whl"))
    venv.create(tmp_path / "venv", with_pip=True)
    bindir = tmp_path / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    subprocess.run([str(python), "-m", "pip", "install", "-q", str(wheel)], check=True)
    done = subprocess.run(
        [str(python), "-c", "import tokli.cli.main, tokli.config; print('ok')"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "ok"
    tokli_cmd = bindir / ("tokli.exe" if os.name == "nt" else "tokli")
    shown = subprocess.run(
        [str(tokli_cmd), "config", "show"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, shown.stderr


@pytest.mark.packaging
@pytest.mark.skipif(
    os.environ.get("RUN_PACKAGING_TESTS") != "1", reason="set RUN_PACKAGING_TESTS=1"
)
def test_wheel_contains_ui_assets(tmp_path: Path) -> None:
    """UI-006 / ADR 0006: the dashboard ships in the wheel, and a clean install resolves IANA
    time zones on every OS (tzdata)."""
    import zipfile

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(tmp_path / "dist"),
            str(ROOT),
        ],
        check=True,
        capture_output=True,
    )
    wheel = next((tmp_path / "dist").glob("tokli-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    ui = sorted(
        p.relative_to(SRC.parent).as_posix()
        for p in (SRC / "ui").rglob("*.*")
        if "__pycache__" not in p.parts
    )
    assert ui and all(name in names for name in ui), sorted(set(ui) - names)
    venv.create(tmp_path / "venv", with_pip=True)
    bindir = tmp_path / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    subprocess.run([str(python), "-m", "pip", "install", "-q", str(wheel)], check=True)
    done = subprocess.run(
        [str(python), "-c", "import zoneinfo; print(zoneinfo.ZoneInfo('Europe/Rome').key)"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "Europe/Rome"


def test_routing_inputs_closed_and_no_ml() -> None:
    import dataclasses

    from tokli.domain.stage import Features

    # The routing inputs are exactly the features of SPEC 011 (S1 subset), the segment view,
    # the compressor specs and the engine settings (AC-RT-4).
    assert {f.name for f in dataclasses.fields(Features)} == {"tokens", "json_candidate"}
    ml = re.compile(r"^\s*(?:import|from)\s+(transformers|torch|onnxruntime|sklearn)\b", re.M)
    storage = re.compile(r"^\s*(?:import|from)\s+(sqlite3|tokli\.telemetry)\b", re.M)
    for path in python_sources(SRC):
        text = path.read_text(encoding="utf-8")
        assert not ml.search(text), path
        if "compression" in path.parts or "compressors" in path.parts:
            assert not storage.search(text), path


def test_repository_contains_no_developer_paths() -> None:
    """No tracked file may contain a personal home path (privacy; CLAUDE.md §9, PT-010)."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    users = "Us" + "ers"
    home_path = re.compile(
        r"[A-Za-z]:[\\/]+" + users + r"[\\/]+(?!dev[\\/]|<)[A-Za-z0-9._-]+[\\/]"
        r"|/" + users + r"/(?!dev/)[a-z][a-z0-9._-]*/"
        r"|/home/(?!dev/|runner/)[a-z][a-z0-9._-]*/"
    )
    offenders = []
    for name in tracked:
        path = ROOT / name
        if path.suffix in {".tiktoken", ".png", ".db"} or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if home_path.search(text):
            offenders.append(name)
    assert offenders == [], offenders
