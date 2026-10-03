"""Entry point of the ``tokli`` command.

Every command accepts the configuration options ``--config``, ``--config-dir``, ``--data-dir`` and
the repeatable ``--set section.key=value`` (SPEC 017, layer 4). Failures print exactly two lines on
stderr, ``error: <cause>`` and ``fix: <fix>``, and exit with status 1 (PT-008).
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from tokli.app.bootstrap import StartupError, bootstrap
from tokli.app.doctor import Environment, build_report, config_lines, render
from tokli.app.serve import ListenError, is_loopback, prepare_listener
from tokli.app.setup_tokenizers import setup_tokenizers
from tokli.config import CliOverrides, ConfigError, EffectiveConfig, load_config
from tokli.telemetry.store import SchemaError

EXIT_OK = 0
EXIT_PROBLEM = 1


def _config_options() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    group = common.add_argument_group("configuration")
    group.add_argument("--config", metavar="PATH", help="config file (overrides TOKLI_CONFIG)")
    group.add_argument("--config-dir", metavar="DIR", help="config directory")
    group.add_argument("--data-dir", metavar="DIR", help="data directory")
    group.add_argument(
        "--set",
        metavar="KEY=VALUE",
        action="append",
        default=[],
        dest="sets",
        help="override one setting, e.g. --set tokens.default=o200k_base (repeatable)",
    )
    return common


def _parser() -> argparse.ArgumentParser:
    common = _config_options()
    parser = argparse.ArgumentParser(prog="tokli", description="Tokli local token-reduction proxy.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    doctor = commands.add_parser("doctor", parents=[common], help="check this installation")
    doctor.add_argument(
        "--normalized",
        action="store_true",
        help="omit machine-specific lines so two installs can be compared",
    )

    config = commands.add_parser("config", help="inspect the configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True, metavar="ACTION")
    config_commands.add_parser(
        "show", parents=[common], help="effective settings and their sources"
    )

    serve = commands.add_parser("serve", parents=[common], help="run the proxy")
    serve.add_argument("--port", metavar="PORT", help="listen port (0 = any free port)")
    serve.add_argument(
        "--allow-remote", action="store_true", help="allow a non-loopback listen address"
    )
    serve.add_argument("--log-format", choices=["json", "text"], help="log line format")

    setup = commands.add_parser("setup", help="provision local data")
    setup_commands = setup.add_subparsers(dest="setup_command", required=True, metavar="WHAT")
    tokenizers = setup_commands.add_parser(
        "tokenizers", parents=[common], help="download (or copy) and verify tokenizer files"
    )
    tokenizers.add_argument(
        "--from-file",
        metavar="PATH",
        action="append",
        default=[],
        dest="from_files",
        help="use a local .tiktoken file instead of downloading (repeatable)",
    )
    return parser


def _environment() -> Environment:
    try:
        version = metadata.version("tokli")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return Environment(
        tokli_version=version,
        python=f"{platform.python_version()} ({platform.python_implementation()})",
        platform=f"{platform.system()} {platform.release()} {platform.machine()}",
    )


def _load(args: argparse.Namespace) -> EffectiveConfig:
    named: list[tuple[str, str, str]] = []
    if getattr(args, "port", None) is not None:
        named.append(("server.port", args.port, "--port"))
    if getattr(args, "allow_remote", False):
        named.append(("server.allow_remote", "true", "--allow-remote"))
    if getattr(args, "log_format", None):
        named.append(("observability.log_format", args.log_format, "--log-format"))
    cli = CliOverrides(
        config_file=args.config,
        config_dir=args.config_dir,
        data_dir=args.data_dir,
        sets=tuple(args.sets),
        named=tuple(named),
    )
    return load_config(cli, os.environ, sys.platform)


def _run(args: argparse.Namespace) -> int:
    config = _load(args)
    if args.command == "doctor":
        report = build_report(config, _environment())
        print(render(report, normalized=args.normalized), end="")
        return EXIT_OK if report.ok else EXIT_PROBLEM
    if args.command == "serve":
        return _serve(config)
    if args.command == "config":
        for line in config_lines(config, normalized=False):
            print(line.strip())
        print(f"config hash: {config.config_hash}")
        return EXIT_OK
    for result in setup_tokenizers(config, from_files=[Path(p) for p in args.from_files]):
        print(f"{result.name}: {result.action} -> {result.path}")
    return EXIT_OK


def _serve(config: EffectiveConfig) -> int:
    import uvicorn

    from tokli.http.app import create_app
    from tokli.observability.logs import configure_log_file, configure_logging

    sock = prepare_listener(config)
    try:
        version = _environment().tokli_version
        services = bootstrap(config, version=version)
        if services.store is not None:
            services.store.start()
    except BaseException:
        sock.close()
        raise
    handlers = [configure_logging(config.settings.observability.log_format)]
    if config.settings.observability.log_file:  # OB-013
        log_file = configure_log_file(config.dirs.data_dir / "logs" / "tokli.log")
        if log_file is None:
            print("warning: cannot open the log file; logging to stderr only", file=sys.stderr)
        else:
            handlers.append(log_file)
    host, port = sock.getsockname()[:2]
    dirs = config.dirs
    print(
        f"Tokli {version} listening on http://{host}:{port}/anthropic", file=sys.stderr, flush=True
    )
    print(f"dashboard: http://{host}:{port}/tokli/", file=sys.stderr)  # UI-011
    print(f"config dir: {dirs.config_dir} [{dirs.config_dir_source}]", file=sys.stderr)
    print(f"data dir:   {dirs.data_dir} [{dirs.data_dir_source}]", file=sys.stderr, flush=True)
    if not is_loopback(config.settings.server.host):
        print("warning: listening on a non-loopback address (--allow-remote)", file=sys.stderr)
    app = create_app(services, listen=f"{host}:{port}")
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=None, access_log=False, lifespan="on", log_level="warning")
    )
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass  # Ctrl+C: uvicorn shut down gracefully, then re-raised the signal
    finally:
        if services.store is not None:
            services.store.close()  # idempotent; flushes pending telemetry
        sock.close()
        for handler in handlers:
            logging.getLogger().removeHandler(handler)
            handler.close()
    print("Tokli stopped", file=sys.stderr, flush=True)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")  # MD-16: never crash on a legacy console encoding
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (ConfigError, StartupError, ListenError) as exc:
        print(f"error: {exc.cause}", file=sys.stderr)
        print(f"fix: {exc.fix}", file=sys.stderr)
        return EXIT_PROBLEM
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("fix: use a newer Tokli or choose another --data-dir", file=sys.stderr)
        return EXIT_PROBLEM


if __name__ == "__main__":
    raise SystemExit(main())
