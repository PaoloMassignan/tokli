"""`tokli serve`: startup failures (TM-006, PT-008, PX-001) and a real process (fresh-machine
scenarios "alternative port" and "hostile environment", serve variant)."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.conftest import Cli
from tests.helpers import PROVISIONED_DATA_DIR, home_env


def test_serve_missing_tokenizer_fails_clearly(cli: Cli) -> None:
    data_dir = cli.workdir / "empty-data"
    result = cli.run("serve", "--data-dir", str(data_dir), "--port", "0")
    assert result.code == 1
    lines = result.err.strip().splitlines()
    assert lines[0].startswith("error: tokenizer o200k_base missing: expected ")
    assert str(data_dir) in lines[0]
    assert lines[1] == "fix: run 'tokli setup tokenizers'"


def test_serve_port_in_use_fails_clearly(cli: Cli) -> None:
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    port = busy.getsockname()[1]
    try:
        result = cli.run("serve", "--port", str(port))
    finally:
        busy.close()
    assert result.code == 1
    assert f"port {port}" in result.err and "--port" in result.err


def test_serve_remote_bind_needs_flag(cli: Cli) -> None:
    result = cli.run("serve", "--set", "server.host=0.0.0.0", "--port", "0")
    assert result.code == 1 and "--allow-remote" in result.err


def test_serve_ctrl_c_stops_cleanly(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression (found in live test E1a, 2026-10-02): Ctrl+C printed a KeyboardInterrupt
    traceback. Root cause: after a graceful shutdown uvicorn re-raises the captured SIGINT, and
    `tokli serve` did not handle it, so Python printed the traceback and exited with code 130."""
    import uvicorn

    from tests.integration.servers import BYTE_CATALOG, provision
    from tokli.app import bootstrap as bootstrap_module

    data_dir = cli.workdir / "data"
    provision(data_dir)
    real_bootstrap = bootstrap_module.bootstrap
    monkeypatch.setattr(
        "tokli.cli.main.bootstrap",
        lambda config, **kw: real_bootstrap(config, catalog=BYTE_CATALOG, version="test"),
    )
    closed: list[bool] = []

    def interrupted_run(self: uvicorn.Server, sockets: object = None) -> None:
        raise KeyboardInterrupt  # what uvicorn does after a graceful Ctrl+C shutdown

    monkeypatch.setattr(uvicorn.Server, "run", interrupted_run)
    from tokli.telemetry.store import TelemetryStore

    real_close = TelemetryStore.close

    def tracking_close(self: TelemetryStore) -> None:
        closed.append(True)
        real_close(self)

    monkeypatch.setattr(TelemetryStore, "close", tracking_close)
    result = cli.run("serve", "--data-dir", str(data_dir), "--port", "0")
    assert result.code == 0
    assert "Traceback" not in result.err
    assert "Tokli stopped" in result.err
    assert closed  # telemetry flushed and closed on Ctrl+C


@pytest.mark.skipif(PROVISIONED_DATA_DIR is None, reason="set TEST_TOKLI_PROVISIONED_DATA_DIR")
def test_serve_process_end_to_end(tmp_path: Path) -> None:
    assert PROVISIONED_DATA_DIR is not None
    env = {k: v for k, v in os.environ.items() if not k.startswith("TOKLI_")}
    env.update(home_env(tmp_path / "home"))
    env.update({"ANTHROPIC_API_KEY": "junk", "OPENAI_API_KEY": "junk"})  # hostile environment
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tokli.cli.main",
            "serve",
            "--data-dir",
            PROVISIONED_DATA_DIR,
            "--port",
            "0",
            "--log-format",
            "text",
        ],
        cwd=tmp_path,
        env=env,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stderr is not None
        url = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and url is None:
            line = process.stderr.readline()
            match = re.search(r"listening on (http://127\.0\.0\.1:\d+)", line)
            if match:
                url = match.group(1)
        assert url is not None, "no startup line"
        health = httpx.get(url + "/tokli/health", timeout=10).json()
        assert health["status"] == "ok"
        assert health["listen"] == url.removeprefix("http://")
    finally:
        process.terminate()
        process.wait(timeout=15)
