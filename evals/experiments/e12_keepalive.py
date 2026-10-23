"""E12: does a keepalive request keep the provider's prompt cache warm across a pause (S8l)?

Three synthetic conversations of the same size (about 64,000 provider tokens, Claude Code's shape: a
system prompt, tool definitions, a coding conversation, one-hour cache markers on the system
prompt and on the last block) are sent at the start:
- `plain`: no extended thinking;
- `thinking`: extended thinking, as an agent may send it (`--thinking adaptive`, the default, or
  `--thinking enabled` with a budget);
- `control`: like `plain`, never pinged.

Then:
1. **Ping**, at the cache lifetime minus 5 minutes, for `plain` and `thinking`: the same body as
   the first request, byte for byte, except `max_tokens` (1; with `--thinking enabled`, the
   smallest value the API accepts above the thinking budget).
2. **Return**, at twice the cache lifetime minus 10 minutes, for all three: the first request's
   messages, plus a fixed assistant reply and a new user turn (the marker moves to the new last
   block, as an agent does).

Each run starts with a random nonce in the system prompt, so caches of earlier runs never match.

Per call it records the time, the HTTP status, `stop_reason` and the usage (input, cache read,
cache write by lifetime, output). No content of a response is kept.

Decision rule, fixed before the run:
- (a) a ping reads the prefix: its cache read is at least 95 % of the first request's input, and
  its cache write at most 5 %;
- (b) the pinged returns are warm (cache read at least 95 % of the first request's input) and the
  control's return is cold (cache write at least 95 %);
- (c) the ping's output tokens and cost are recorded, for the requirement text.
**Go** for S8l if (a) and (b) hold for `plain`. The `thinking` result decides how a ping copies
thinking settings.

The API key is read only from the environment variable named by `--api-key-env`; it is never
printed or written. `--dry-run` sends nothing and prints the plan and an estimated cost.
`--ttl 5m` runs the same timeline with five-minute markers in about 10 minutes, to check the
script before the one-hour run (about 2 hours).

Usage:
    python evals/experiments/e12_keepalive.py --dry-run
    python evals/experiments/e12_keepalive.py --api-key-env NAME --ttl 5m
    python evals/experiments/e12_keepalive.py --api-key-env NAME
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import sys
import time
from pathlib import Path
from typing import Any

SEED = 20261022
TARGET_CHARS = 120_000  # about 64,000 tokens (numbers and tabs tokenize densely)
TTL_SECONDS = {"5m": 300, "1h": 3600}
THINKING_BUDGET = 1024
THINKING = "adaptive"  # set from --thinking
PRICE = {"input": 4.0, "write_5m": 5.0, "write_1h": 8.0, "read": 0.20, "output": 20.0}

TOOLS = [
    {
        "name": "Read",
        "description": "Read a file from the local filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "Bash",
        "description": "Run a shell command and return its output.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "Edit",
        "description": "Replace an exact string in a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
]


def module(rng: random.Random, index: int) -> str:
    lines = [f'"""Synthetic module {index}."""', ""]
    for f in range(12):
        name = f"step_{index}_{f}_{rng.randrange(10**6)}"
        lines.append(f"def {name}(value: int, limit: int = {rng.randrange(100)}) -> int:")
        for b in range(8):
            lines.append(f"    value = (value * {rng.randrange(2, 97)} + {b}) % (limit + 7)")
        lines += ["    return value", "", ""]
    return "\n".join(f"{n}\t{line}" for n, line in enumerate(lines, start=1))


def conversation(variant: str, nonce: str) -> list[dict[str, Any]]:
    rng = random.Random(f"{SEED}-{variant}")
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Look at the step modules and tell me what they compute."}
    ]
    size, index = 0, 0
    while size < TARGET_CHARS:
        text = module(rng, index)
        call = f"toolu_e12_{variant}_{index}"
        messages += [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call,
                        "name": "Read",
                        "input": {"file_path": f"src/steps/mod_{index}.py"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": call, "content": text}],
            },
        ]
        size += len(text)
        index += 1
    messages[-1]["content"].append(
        {"type": "text", "text": f"Summarise the modules in one sentence. Run {nonce}."}
    )
    return messages


def marked(messages: list[dict[str, Any]], ttl: str) -> list[dict[str, Any]]:
    """A copy with the cache marker on the last block only, as an agent sends it."""
    out = json.loads(json.dumps(messages))
    last = out[-1]["content"]
    if isinstance(last, str):
        out[-1]["content"] = last = [{"type": "text", "text": last}]
    last[-1]["cache_control"] = {"type": "ephemeral", "ttl": ttl}
    return out


def body(
    variant: str, messages: list[dict[str, Any]], nonce: str, ttl: str, model: str, max_tokens: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {
                "type": "text",
                "text": f"Run {nonce}. You are a coding agent working in a repository. "
                "Use the tools to read and change files. Answer briefly.",
                "cache_control": {"type": "ephemeral", "ttl": ttl},
            }
        ],
        "tools": TOOLS,
        "messages": marked(messages, ttl),
    }
    if variant == "thinking":
        payload["thinking"] = (
            {"type": "enabled", "budget_tokens": THINKING_BUDGET}
            if THINKING == "enabled"
            else {"type": "adaptive"}
        )
    return payload


def first_max_tokens(variant: str) -> int:
    return THINKING_BUDGET + 1024 if variant == "thinking" else 1024


def ping_max_tokens(variant: str) -> int:
    if variant == "thinking" and THINKING == "enabled":
        return THINKING_BUDGET + 1  # the API requires max_tokens above the budget
    return 1


def returned(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        *messages,
        {"role": "assistant", "content": "They are arithmetic steps over an integer value."},
        {"role": "user", "content": "Thanks. Which module is the largest? One word."},
    ]


def usage_row(response: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"status": response.status_code, "t": round(time.time(), 1)}
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        row["error_type"] = error.get("type")
        row["error_message"] = str(error.get("message") or "")[:300]  # the provider's text only
        return row
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    creation = usage.get("cache_creation") or {}
    row.update(
        stop_reason=data.get("stop_reason"),
        input=usage.get("input_tokens"),
        cache_read=usage.get("cache_read_input_tokens"),
        cache_write=usage.get("cache_creation_input_tokens"),
        cache_write_5m=creation.get("ephemeral_5m_input_tokens"),
        cache_write_1h=creation.get("ephemeral_1h_input_tokens"),
        output=usage.get("output_tokens"),
    )
    return row


def verdict(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def total(r: dict[str, Any]) -> int:
        return sum(int(r.get(k) or 0) for k in ("input", "cache_read", "cache_write"))

    out: dict[str, Any] = {}
    for variant in ("plain", "thinking"):
        first, ping, back = (rows.get(f"{variant}/{s}", {}) for s in ("first", "ping", "return"))
        base = total(first) or 1
        out[variant] = {
            "a_ping_reads_prefix": bool(ping)
            and int(ping.get("cache_read") or 0) >= 0.95 * base
            and int(ping.get("cache_write") or 0) <= 0.05 * base,
            "b_return_warm": bool(back) and int(back.get("cache_read") or 0) >= 0.95 * base,
            "c_ping_output_tokens": ping.get("output"),
        }
    control, base = rows.get("control/return", {}), total(rows.get("control/first", {})) or 1
    out["control_return_cold"] = (
        bool(control) and int(control.get("cache_write") or 0) >= 0.95 * base
    )
    out["go"] = bool(
        out["plain"]["a_ping_reads_prefix"]
        and out["plain"]["b_return_warm"]
        and out["control_return_cold"]
    )
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-key-env")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--ttl", choices=sorted(TTL_SECONDS), default="1h")
    parser.add_argument("--thinking", choices=("adaptive", "enabled"), default="adaptive")
    parser.add_argument("--dry-run", action="store_true", help="send nothing; print the plan")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "e12_result.json"))
    args = parser.parse_args(argv)
    global THINKING
    THINKING = args.thinking
    ttl, life = args.ttl, TTL_SECONDS[args.ttl]
    ping_at, return_at = (
        life - 300 if life > 600 else life - 60,
        2 * life - 600 if life > 600 else 2 * life - 120,
    )
    variants = ("plain", "thinking", "control")
    nonce = secrets.token_hex(6)
    convs = {v: conversation(v, nonce) for v in variants}
    if args.dry_run:
        tokens = sum(len(json.dumps(m)) for m in convs.values()) / 2  # measured on E12 5m run
        write = PRICE[f"write_{ttl}"]
        est = (tokens * write + tokens / 3 * write + tokens * 3 * PRICE["read"]) / 1e6 + 0.10
        print(
            f"3 conversations of about {tokens / 3:,.0f} tokens; first requests at 0 s, pings at "
            f"{ping_at} s, returns at {return_at} s ({ttl} markers); 8 calls; "
            f"estimated cost ${est:.2f} on {args.model}"
        )
        return 0
    key = os.environ.get(args.api_key_env or "", "")
    if not key:
        print("error: pass --api-key-env with a non-empty variable, or --dry-run", file=sys.stderr)
        return 2
    import httpx

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    rows: dict[str, dict[str, Any]] = {}
    start = time.time()

    def save() -> None:
        Path(args.out).write_text(
            json.dumps(
                {
                    "model": args.model,
                    "ttl": ttl,
                    "thinking": THINKING,
                    "rows": rows,
                    "verdict": verdict(rows),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def send(name: str, payload: dict[str, Any]) -> None:
        try:
            response = client.post(
                "https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=300
            )
            row = usage_row(response)
        except httpx.HTTPError as exc:  # a network failure is recorded, and the run goes on
            row = {"status": None, "t": round(time.time(), 1), "error_type": type(exc).__name__}
        row["at_s"] = round(time.time() - start)
        rows[name] = row
        save()
        print(
            json.dumps(
                {
                    "call": name,
                    **{
                        k: row.get(k)
                        for k in ("at_s", "status", "cache_read", "cache_write", "output")
                    },
                }
            )
        )

    def wait_until(offset: int) -> None:
        delay = start + offset - time.time()
        if delay > 0:
            print(f"waiting {delay / 60:.1f} min")
            time.sleep(delay)

    with httpx.Client() as client:
        for v in variants:
            send(f"{v}/first", body(v, convs[v], nonce, ttl, args.model, first_max_tokens(v)))
        wait_until(ping_at)
        for v in ("plain", "thinking"):
            send(f"{v}/ping", body(v, convs[v], nonce, ttl, args.model, ping_max_tokens(v)))
        wait_until(return_at)
        for v in variants:
            send(
                f"{v}/return",
                body(v, returned(convs[v]), nonce, ttl, args.model, first_max_tokens(v)),
            )
    save()
    print(json.dumps(verdict(rows), indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
