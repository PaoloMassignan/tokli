"""E2: does Tokli's money saving match what the provider actually charges, after its cache?

(S6, P6; TOKLI_TEST_STRATEGY §7.)

A scripted, synthetic agent conversation is sent turn by turn through two real Tokli instances:
- `baseline`, with every compressor off;
- `candidate`, with the default compressors.

Each turn adds a JSON tool result and a file read; every other turn the file is edited and read
again. Each request carries a cache breakpoint on its last block, as coding agents do, so the
provider caches the growing history.

Two figures are compared:
- **observed:** the input-side cost of the baseline arm minus that of the candidate arm, from
  the provider's own usage at the price book;
- **predicted:** the money saving that the candidate Tokli reports (`/tokli/api/metrics/summary`,
  method `positional`).

The run passes when they agree within ±25 %.

`--dry-run` replaces the provider with an in-process simulation of its prompt cache: it reads
the longest prefix cached by an earlier request, writes up to the request's last breakpoint,
and sends the rest uncached. The dry run costs nothing and checks the method end to end.

The content is synthetic. The API key is read only from the environment variable named by
`--api-key-env`; it is never printed or written.

Usage:
    python evals/experiments/e2_cache_economics.py --dry-run
    python evals/experiments/e2_cache_economics.py --api-key-env NAME [--model ID] [--turns N]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import shutil
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from tokli.app.bootstrap import bootstrap
from tokli.app.metrics import MetricsQuery, parse_filters
from tokli.compression.registry import REGISTRY
from tokli.config import CliOverrides, load_config
from tokli.http.app import create_app
from tokli.pricing.cost import UsageTokens, forwarded_cost
from tokli.telemetry import queries
from tokli.tokens import CATALOG, tokenizer_dir

ANTHROPIC = "https://api.anthropic.com"
TOLERANCE = 0.25
MAX_TOKENS = 16
WORDS = [
    "amber",
    "birch",
    "cobalt",
    "delta",
    "ember",
    "fjord",
    "garnet",
    "harbor",
    "indigo",
    "juniper",
    "kelp",
    "lumen",
    "marble",
    "nectar",
    "onyx",
    "pebble",
    "quartz",
    "river",
    "saffron",
    "tundra",
    "umber",
    "violet",
    "willow",
    "xenon",
    "yarrow",
    "zephyr",
]

# -- the provider's prompt cache, simulated (dry run only) -------------------------------------

Block = tuple[str, int, bool]  # (content key, tokens, cache breakpoint after it)


class SimulatedCache:
    """Prefix caching as the provider documents it: a request reads the longest prefix that an
    earlier request cached (looking back from its breakpoints), writes from there up to its own
    last breakpoint, and sends the rest uncached. Each breakpoint caches the prefix up to it."""

    def __init__(self) -> None:
        self._prefixes: set[str] = set()

    @staticmethod
    def _keys(blocks: list[Block]) -> list[str]:
        digest = hashlib.sha256()
        keys = []
        for key, _, _ in blocks:
            digest.update(hashlib.sha256(key.encode("utf-8")).digest())
            keys.append(digest.copy().hexdigest())
        return keys

    def usage(self, blocks: list[Block]) -> dict[str, int]:
        keys = self._keys(blocks)
        read_to = 0
        for i, key in enumerate(keys):
            if key in self._prefixes:
                read_to = i + 1
        breakpoints = [i for i, (_, _, bp) in enumerate(blocks) if bp]
        write_to = max(read_to, breakpoints[-1] + 1) if breakpoints else read_to
        tokens = [n for _, n, _ in blocks]
        for i in breakpoints:
            self._prefixes.add(keys[i])
        return {
            "read": sum(tokens[:read_to]),
            "write": sum(tokens[read_to:write_to]),
            "input": sum(tokens[write_to:]),
        }


def blocks_of(body: Mapping[str, Any]) -> list[Block]:
    """The request as the provider sees its prefix: tools, system, then message blocks. A block
    counts one token per UTF-8 byte of its JSON without `cache_control` (the dry run's unit)."""
    items: list[dict[str, Any]] = []
    for tool in body.get("tools", []):
        items.append(tool)
    system = body.get("system")
    if isinstance(system, str):
        items.append({"type": "text", "text": system})
    elif isinstance(system, list):
        items.extend(system)
    for message in body.get("messages", []):
        content = message["content"]
        if isinstance(content, str):
            items.append({"type": "text", "text": content, "role": message["role"]})
        else:
            items.extend({**block, "role": message["role"]} for block in content)
    out: list[Block] = []
    for item in items:
        plain = {k: v for k, v in item.items() if k != "cache_control"}
        key = json.dumps(plain, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        out.append((key, len(key.encode("utf-8")), "cache_control" in item))
    return out


def simulated_provider() -> Any:
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    cache = SimulatedCache()
    lock = threading.Lock()

    async def messages(request: Request) -> JSONResponse:
        body = json.loads(await request.body())
        with lock:
            used = cache.usage(blocks_of(body))
        return JSONResponse(
            {
                "id": "msg_simulated",
                "type": "message",
                "role": "assistant",
                "model": body.get("model"),
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": used["input"],
                    "cache_read_input_tokens": used["read"],
                    "cache_creation_input_tokens": used["write"],
                    "output_tokens": 1,
                },
            }
        )

    return Starlette(routes=[Route("/v1/messages", messages, methods=["POST"])])


# -- the scripted conversation -----------------------------------------------------------------


def _module(rng: random.Random, lines: int) -> list[str]:
    out = []
    for n in range(lines):
        if n % 12 == 0:
            out.append(f"def {rng.choice(WORDS)}_{n}(value):")
        else:
            out.append(f"    value = value + {rng.randint(1, 99)}  # {rng.choice(WORDS)}")
    return out


def _numbered(lines: list[str]) -> str:
    return "".join(f"{n:>6}\t{line}\n" for n, line in enumerate(lines, start=1))


def conversation(turns: int, nonce: str) -> Iterator[dict[str, Any]]:
    """One request body per turn; each ends with the turn's last tool result, which carries the
    cache breakpoint (the system prompt carries one too)."""
    rng = random.Random(2026)
    system_text = f"Run {nonce}.\n" + " ".join(rng.choice(WORDS) for _ in range(3500))
    system = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]
    history: list[dict[str, Any]] = []
    module = _module(rng, 160)
    for turn in range(turns):
        listing = json.dumps(
            [
                {"id": n, "name": f"{rng.choice(WORDS)}-{turn}-{n}", "tags": rng.sample(WORDS, 3)}
                for n in range(30)
            ],
            indent=2,
        )
        calls = [
            ("mcp__inventory__list", {}, listing),
            ("Read", {"file_path": "src/module.py"}, _numbered(module)),
        ]
        if turn % 2 == 1:
            line = rng.randrange(1, len(module))
            old, new = module[line], module[line] + "  # changed"
            module = [*module[:line], new, *module[line + 1 :]]
            calls += [
                (
                    "Edit",
                    {"file_path": "src/module.py", "old_string": old, "new_string": new},
                    "The file src/module.py has been updated.",
                ),
                ("Read", {"file_path": "src/module.py"}, _numbered(module)),
            ]
        history.append({"role": "user", "content": f"Synthetic step {turn}: continue the task."})
        for i, (name, arguments, result) in enumerate(calls):
            call_id = f"toolu_{turn:02d}_{i}"
            history.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
                    ],
                }
            )
            history.append(
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": call_id, "content": result}],
                }
            )
        messages = copy.deepcopy(history)
        messages[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        yield {"model": "", "max_tokens": MAX_TOKENS, "system": system, "messages": messages}


# -- running the arms through real Tokli instances ---------------------------------------------


@contextmanager
def _serve(app: Any) -> Iterator[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=None, access_log=False, lifespan="on", log_level="warning")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("server did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("TOKLI_")}


def copy_user_tokenizers(data_dir: Path) -> None:
    """Real runs: the tokenizers already provisioned in the default data directory."""
    default = load_config(CliOverrides(), _clean_env(), sys.platform).dirs.data_dir
    shutil.copytree(tokenizer_dir(default), tokenizer_dir(data_dir), dirs_exist_ok=True)


def _input_cost(prices: Any, row: Mapping[str, Any]) -> Decimal:
    usage = UsageTokens(
        input=int(row["usage_input"] or 0),
        cache_read=int(row["usage_cache_read"] or 0),
        cache_write_5m=int(row["usage_cache_write_5m"] or 0),
        cache_write_1h=int(row["usage_cache_write_1h"] or 0),
        output=0,  # TC-007: output is never a compression saving
    )
    return forwarded_cost(prices, usage)


def run_arms(
    upstream: str,
    api_key: str,
    model: str,
    turns: int,
    root: Path,
    *,
    catalog: Mapping[str, Any] = CATALOG,
    provision: Callable[[Path], None] = copy_user_tokenizers,
    out: Callable[[str], None] = print,
) -> dict[str, Any]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    started = datetime.now(UTC) - timedelta(minutes=1)
    arms: dict[str, dict[str, Any]] = {}
    for arm, sets in (
        ("baseline", tuple(f"compressors.{c.spec.id}.enabled=false" for c in REGISTRY)),
        ("candidate", ()),
    ):
        data_dir = root / arm
        provision(data_dir)
        config = load_config(
            CliOverrides(
                data_dir=str(data_dir),
                config_dir=str(root / "no-config"),
                sets=(f"upstreams.anthropic.base_url={upstream}", *sets),
            ),
            _clean_env(),
            sys.platform,
        )
        services = bootstrap(config, catalog=catalog, version="e2")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with _serve(create_app(services)) as url:
            for turn, body in enumerate(conversation(turns, f"{run_id}-{arm}")):
                body["model"] = model
                response = httpx.post(
                    url + "/anthropic/v1/messages",
                    content=json.dumps(body),
                    headers=headers,
                    timeout=600,
                )
                if response.status_code != 200:
                    raise SystemExit(f"{arm} turn {turn}: HTTP {response.status_code}")
                out(f"{arm}: turn {turn + 1}/{turns} sent")
                time.sleep(0.05)
            deadline = time.monotonic() + 30
            assert services.store is not None
            while time.monotonic() < deadline:
                services.store.flush()
                rows = queries.requests_between(
                    services.store.path, started, datetime.now(UTC) + timedelta(minutes=1)
                )
                if len(rows) >= turns:
                    break
                time.sleep(0.1)
            window = {
                "from": started.isoformat(),
                "to": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            }
            summary = MetricsQuery(services.store.path, prices=services.prices).summary(
                parse_filters(window)
            )
        match = services.prices.lookup(model, datetime.now(UTC))
        if match is None:
            raise SystemExit(f"no price for {model} in the price book")
        arms[arm] = {
            "requests": len(rows),
            "input_cost_usd": sum((_input_cost(match.prices, r) for r in rows), Decimal(0)),
            "saved": summary["cost"]["saved"],
            "tokens_saved": summary["tokens"]["saved"],
            "price_book_version": match.version,
        }
    observed = arms["baseline"]["input_cost_usd"] - arms["candidate"]["input_cost_usd"]
    predicted = arms["candidate"]["saved"]
    estimate = Decimal(str(predicted.get("estimate", 0) or 0))
    relative = float((estimate - observed) / observed) if observed > 0 else float("inf")
    return {
        "model": model,
        "turns": turns,
        "observed_saving_usd": float(observed),
        "predicted": predicted,
        "relative_error": round(relative, 4),
        "tolerance": TOLERANCE,
        "verdict": "pass" if observed > 0 and abs(relative) <= TOLERANCE else "fail",
        "arms": {
            name: {
                "requests": a["requests"],
                "input_cost_usd": float(a["input_cost_usd"]),
                "tokens_saved": a["tokens_saved"],
            }
            for name, a in arms.items()
        },
        "price_book_version": arms["candidate"]["price_book_version"],
    }


def dry_run(
    root: Path,
    *,
    turns: int = 12,
    catalog: Mapping[str, Any] = CATALOG,
    provision: Callable[[Path], None] = copy_user_tokenizers,
    model: str = "claude-sonnet-5",
    out: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """The whole experiment against the simulated cache: no provider call, no cost."""
    with _serve(simulated_provider()) as upstream:
        return run_arms(
            upstream,
            "sk-ant-api03-E2-DRY-RUN",
            model,
            turns,
            root,
            catalog=catalog,
            provision=provision,
            out=out,
        )


def _ceiling_usd(model: str, turns: int) -> Decimal:
    """Upper bound of a real run: every byte of every request at the 1-hour cache-write price
    (4 bytes ≈ 1 token is generous for this content), plus `max_tokens` of output, both arms."""
    from tokli.pricing.book import PriceTable, load_shipped

    match = PriceTable(load_shipped()).lookup(model, datetime.now(UTC))
    if match is None:
        raise SystemExit(f"no price for {model} in the price book")
    tokens = sum(len(json.dumps(body)) // 3 for body in conversation(turns, "plan"))
    per_arm = (
        tokens * match.prices.cache_write_1h + turns * MAX_TOKENS * match.prices.output
    ) / Decimal(1_000_000)
    return 2 * per_arm


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="simulated provider: no cost")
    parser.add_argument(
        "--api-key-env", metavar="NAME", help="environment variable with an Anthropic API key"
    )
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="tokli-e2-") as tmp:
        if args.dry_run:
            result = dry_run(Path(tmp), turns=args.turns, model=args.model, out=print)
        else:
            if not args.api_key_env or not os.environ.get(args.api_key_env):
                raise SystemExit(
                    "set --api-key-env NAME to a variable holding an Anthropic API key"
                )
            calls = 2 * args.turns
            print(
                f"Plan: {calls} calls to {args.model} ({args.turns} turns x 2 arms); "
                f"estimated cost: at most ${_ceiling_usd(args.model, args.turns):.2f} (upper bound)"
            )
            if not args.yes and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                print("cancelled: no provider call was made")
                return 1
            result = run_arms(
                ANTHROPIC, os.environ[args.api_key_env], args.model, args.turns, Path(tmp)
            )
            target = Path(__file__).with_name("e2_result.json")
            target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(f"result: {target}")
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
