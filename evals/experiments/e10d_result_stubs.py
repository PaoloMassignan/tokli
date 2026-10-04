"""E10(d): do stubs in old *tool results* draw provider refusals? (S8d, before code.)

S8c showed that editing the assistant's own tool-call arguments raises refusals (E10(c)). This
experiment checks the user-side counterpart: the content of an old `Read` result is replaced. It
reuses the synthetic settings files of `evals/cases/reread_after_pruned_edit`, turned into a
conversation where the file arrives as a `Read` result:
- the user asks to look at the file;
- the agent reads it;
- five unrelated exchanges follow;
- the user asks for a value from the file.

Four forms of the old result:
- `original` (control);
- `descriptive`: `[tokli: earlier tool output omitted (<n> tokens)]`;
- `hint`: the same with "— read the file again if you need it";
- `empty`.

Per call it records: HTTP status, `stop_reason`, the outcome (`pass`: the right value or a `Read`
of the right file; `fail`; `refusal`; `empty`) and the tool calls. The answers are to synthetic
questions. The API key is read only from the environment variable named by `--api-key-env`; it
is never printed or written.

Usage: python evals/experiments/e10d_result_stubs.py --api-key-env NAME [--model ID]
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "reread_after_pruned_edit"
CASE_IDS = ["06", "14", "18", "20", "21", "01", "02", "03", "04", "05"]
VARIANTS = ("original", "descriptive", "hint", "empty")


def variant(text: str, kind: str) -> str:
    tokens = max(1, len(text) // 4)
    if kind == "original":
        return text
    if kind == "descriptive":
        return f"[tokli: earlier tool output omitted ({tokens} tokens)]"
    if kind == "hint":
        return (
            f"[tokli: earlier tool output omitted ({tokens} tokens) — "
            "read the file again if you need it]"
        )
    return ""


def conversation(case: dict[str, Any], kind: str, model: str) -> dict[str, Any]:
    request = copy.deepcopy(case["request"])
    messages = request["messages"]
    write = messages[1]["content"][0]
    path, content = write["input"]["file_path"], write["input"]["content"]
    read = [
        {"role": "user", "content": f"Show me {path}."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01E10DREAD",
                    "name": "Read",
                    "input": {"file_path": path},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_01E10DREAD",
                    "content": variant(content, kind),
                }
            ],
        },
        {"role": "assistant", "content": f"That is {path}."},
    ]
    request["messages"] = read + messages[4:]  # the small talk and the final question
    return {**request, "model": model}


def outcome(body: dict[str, Any], case: dict[str, Any]) -> tuple[str, list[Any]]:
    blocks = body.get("content", [])
    calls = [(b.get("name"), b.get("input")) for b in blocks if b.get("type") == "tool_use"]
    text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if body.get("stop_reason") == "refusal":
        return "refusal", calls
    if text:
        last = [line.strip().strip("`\"'") for line in text.splitlines() if line.strip()][-1:]
        if last and last[0] == case["expected"]:
            return "pass", calls
    if any(
        name == "Read"
        and isinstance(args, dict)
        and args.get("file_path") == case["expected_read_path"]
        for name, args in calls
    ):
        return "pass", calls
    return ("fail" if text or calls else "empty"), calls


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "e10d_result.json"))
    args = parser.parse_args(argv)
    key = os.environ.get(args.api_key_env, "")
    if not key:
        print(f"error: environment variable {args.api_key_env} is empty", file=sys.stderr)
        return 2
    cases = {
        cid: yaml.safe_load((CASES / f"{cid}.yaml").read_text(encoding="utf-8")) for cid in CASE_IDS
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    rows: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for repetition in range(args.repetitions):
            for cid, case in cases.items():
                for kind in VARIANTS:
                    response = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=conversation(case, kind, args.model),
                        timeout=120,
                    )
                    row: dict[str, Any] = {
                        "case": cid,
                        "variant": kind,
                        "repetition": repetition + 1,
                        "status": response.status_code,
                    }
                    try:
                        body = response.json()
                    except ValueError:
                        body = {}
                    if response.status_code >= 400:
                        error = body.get("error", {}) if isinstance(body, dict) else {}
                        row.update(outcome="http_error", error_type=error.get("type"))
                    else:
                        result, calls = outcome(body, case)
                        row.update(
                            outcome=result, stop_reason=body.get("stop_reason"), tool_calls=calls
                        )
                    rows.append(row)
                    print(
                        json.dumps(
                            {k: row[k] for k in ("case", "variant", "repetition", "outcome")}
                        )
                    )
    summary = {
        kind: dict(collections.Counter(r["outcome"] for r in rows if r["variant"] == kind))
        for kind in VARIANTS
    }
    Path(args.out).write_text(
        json.dumps({"model": args.model, "summary": summary, "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
