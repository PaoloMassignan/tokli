"""PX-001, PT-008 (listener) and UP-008 (TLS verification) units."""

from __future__ import annotations

import socket
import ssl
from pathlib import Path

import pytest

from tests.helpers import home_env, platform_name
from tokli.app.serve import ListenError, is_loopback, prepare_listener
from tokli.config import CliOverrides, load_config
from tokli.upstream.forwarder import ssl_context


def config(tmp_path: Path, *sets: str):  # type: ignore[no-untyped-def]
    return load_config(CliOverrides(sets=sets), home_env(tmp_path / "home"), platform_name())


def test_default_bind_is_loopback(tmp_path: Path) -> None:
    sock = prepare_listener(config(tmp_path, "server.port=0"))
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
    finally:
        sock.close()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.invalid"])
def test_remote_bind_requires_flag(tmp_path: Path, host: str) -> None:
    with pytest.raises(ListenError) as info:
        prepare_listener(config(tmp_path, f"server.host={host}", "server.port=0"))
    assert "--allow-remote" in info.value.fix


def test_loopback_names() -> None:
    assert is_loopback("127.0.0.1") and is_loopback("localhost") and is_loopback("::1")
    assert not is_loopback("0.0.0.0") and not is_loopback("10.0.0.1")


def test_port_in_use_fails_clearly(tmp_path: Path) -> None:
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    port = busy.getsockname()[1]
    try:
        with pytest.raises(ListenError) as info:
            prepare_listener(config(tmp_path, f"server.port={port}"))
        assert str(port) in info.value.cause
        assert "--port" in info.value.fix
    finally:
        busy.close()


def test_alternative_port(tmp_path: Path) -> None:
    sock = prepare_listener(config(tmp_path, "server.port=0"))
    try:
        assert sock.getsockname()[1] > 0
    finally:
        sock.close()


def test_tls_verification_default_on() -> None:
    context = ssl_context(None)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_tls_custom_ca_bundle_missing_fails(tmp_path: Path) -> None:
    with pytest.raises((OSError, ssl.SSLError)):
        ssl_context(str(tmp_path / "missing.pem"))
