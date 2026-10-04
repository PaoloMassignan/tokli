"""E10(a): does the Anthropic Messages API accept a history whose `Write`/`Edit` arguments were
replaced by Tokli's stub, and what does the model do next? (S8c, SPEC 019 PR-022.)

A synthetic conversation: the agent writes `config.py`, edits it, and several human turns later
is asked for a value from the file. Two variants are sent, each twice:
- `original`: the history as the client sent it;
- `stubbed`: the `content`, `old_string` and `new_string` of the old calls replaced by the stub.

Printed and written: HTTP status, the provider's error type and message (on 4xx), `stop_reason`,
the tool calls requested, the final text answer (the content is synthetic) and the input usage.
The API key is read only from the environment variable named by `--api-key-env`; it is never
printed or written.

Usage: python evals/experiments/e10a_api_acceptance.py --api-key-env NAME [--model ID] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

STUB = "[tokli: earlier edit content omitted ({n} tokens) — read the file for its current state]"
CONTENT = (
    '"""Synthetic service settings."""\n\n'
    'TIMEOUT_S = 30\nRETRIES = 4\nENDPOINT = "https://api.example.invalid/v2"\nBATCH = 128\n'
)
TOOLS = [
    {
        "name": "Write",
        "description": "Writes a file.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "Edit",
        "description": "Replaces old_string with new_string in a file.",
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
    {
        "name": "Read",
        "description": "Reads a file and returns its content.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
]


def stub(text: str) -> str:
    return STUB.format(n=max(1, len(text) // 4))


def conversation(stubbed: bool) -> list[dict[str, Any]]:
    write_content = stub(CONTENT) if stubbed else CONTENT
    old, new = "TIMEOUT_S = 30", "TIMEOUT_S = 45"
    edit_old, edit_new = (stub(old), stub(new)) if stubbed else (old, new)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Create config.py with the service settings we discussed."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_e10a_w1",
                    "name": "Write",
                    "input": {"file_path": "config.py", "content": write_content},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_e10a_w1", "content": "File created."}
            ],
        },
        {"role": "assistant", "content": "Created config.py."},
        {"role": "user", "content": "Raise the timeout to 45 seconds."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_e10a_e1",
                    "name": "Edit",
                    "input": {
                        "file_path": "config.py",
                        "old_string": edit_old,
                        "new_string": edit_new,
                    },
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_e10a_e1", "content": "File edited."}
            ],
        },
        {"role": "assistant", "content": "Done: the timeout is now 45 seconds."},
    ]
    for question, answer in (
        (
            "Thanks. Unrelated: what does HTTP 429 mean?",
            "Too Many Requests: the client is rate limited.",
        ),
        ("And 503?", "Service Unavailable."),
        ("OK.", "Anything else?"),
        ("Let me think about it.", "Sure."),
    ):
        messages += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    messages.append(
        {
            "role": "user",
            "content": "What is the value of RETRIES in config.py right now? Reply with the number "
            "only, or read the file first if you are not sure.",
        }
    )
    return messages


def call(client: httpx.Client, key: str, model: str, stubbed: bool) -> dict[str, Any]:
    response = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": model, "max_tokens": 200, "tools": TOOLS, "messages": conversation(stubbed)},
        timeout=120,
    )
    row: dict[str, Any] = {
        "variant": "stubbed" if stubbed else "original",
        "status": response.status_code,
    }
    try:
        body = response.json()
    except ValueError:
        return {**row, "error": "unparsed body"}
    if response.status_code >= 400:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return {
            **row,
            "error_type": error.get("type"),
            "error_message": str(error.get("message", ""))[:300],
        }
    blocks = body.get("content", [])
    row["stop_reason"] = body.get("stop_reason")
    row["tool_calls"] = [
        {"name": b.get("name"), "input": b.get("input")}
        for b in blocks
        if b.get("type") == "tool_use"
    ]
    row["text"] = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()[
        :300
    ]
    usage = body.get("usage", {})
    row["input_tokens"] = usage.get("input_tokens")
    return row


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "e10a_result.json"))
    args = parser.parse_args(argv)
    key = os.environ.get(args.api_key_env, "")
    if not key:
        print(f"error: environment variable {args.api_key_env} is empty", file=sys.stderr)
        return 2
    rows = []
    with httpx.Client() as client:
        for _ in range(args.repetitions):
            for stubbed in (False, True):
                row = call(client, key, args.model, stubbed)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False))
    Path(args.out).write_text(
        json.dumps({"model": args.model, "rows": rows}, indent=2), encoding="utf-8"
    )
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
