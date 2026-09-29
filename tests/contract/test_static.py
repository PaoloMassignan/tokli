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
