"""E10(e): can a re-read after an edit send only the changed lines, and refer to an earlier read
for the unchanged ones? (Before any S8e code.)

A synthetic conversation per case:
1. The agent reads `<module>.py` (about 250 lines; `cat -n` style line numbers).
2. The user asks for a change in one function. The agent edits it: one line becomes two, so
   the later line numbers shift by one. The agent then reads the file again.
3. The user asks to change the line that holds a marker. That line is in another function,
   **unchanged** and far from the edit, so its exact text appears in full only in the first read
   when the second read refers to it.

Three forms of the second read:
- `full`: the whole new file (control);
- `reference`: every unchanged run of at least 5 lines becomes
  `[tokli: lines a-b unchanged — identical to lines c-d of the read in call <id>]`; the changed
  lines stay in full;
- `reference_symbols`: the same, and each note also names the functions in the run.

Outcome of each call:
- `pass`: an `Edit` of the right file whose `old_string` occurs exactly once in the current
  file and holds the marker line;
- `bad_anchor`: an `Edit` whose `old_string` does not occur in the current file (the failure
  that matters);
- `reread`: the model reads the file again first;
- `other`, `refusal`.

The content is synthetic. The API key is read only from the environment variable named by
`--api-key-env`; it is never printed or written.

Usage: python evals/experiments/e10e_reread_by_reference.py --api-key-env NAME [--model ID]
"""

from __future__ import annotations

import argparse
import collections
import difflib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

import httpx

VARIANTS = ("full", "reference", "reference_symbols")
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
]
READ_1, EDIT, READ_2 = "toolu_01E10EREAD1", "toolu_01E10EEDIT1", "toolu_01E10EREAD2"
TOOLS = [
    {
        "name": "Read",
        "description": "Reads a file and returns its content with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "Edit",
        "description": "Replaces old_string with new_string in a file. "
        "old_string must match the file exactly, without line numbers.",
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


def module(rng: random.Random, marker: str, marked: int) -> list[str]:
    lines = ['"""Synthetic service module."""', "", "import math", ""]
    for n in range(36):
        name = f"{rng.choice(WORDS)}_{n:02d}"
        lines += [
            f"def {name}(value, factor={rng.randint(2, 9)}):",
            f'    """Compute the {rng.choice(WORDS)} score."""',
            f"    base = value * factor + {rng.randint(1, 99)}",
        ]
        if n == marked:
            lines.append(f"    timeout = {rng.randint(10, 60)}  # {marker}")
        lines += [
            f"    if base > {rng.randint(100, 900)}:",
            "        base = math.sqrt(base)",
            "    return base",
            "",
        ]
    return lines


def numbered(lines: list[str], first: int = 1) -> list[str]:
    return [f"{n:>6}\t{line}" for n, line in enumerate(lines, start=first)]


def symbols(lines: list[str]) -> list[str]:
    return [line.split("(")[0][4:] for line in lines if line.startswith("def ")]


def by_reference(old: list[str], new: list[str], with_symbols: bool) -> str:
    out: list[str] = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" and j2 - j1 >= 5:
            note = (
                f"[tokli: lines {j1 + 1}-{j2} unchanged — identical to lines {i1 + 1}-{i2} "
                f"of the read in call {READ_1}"
            )
            names = symbols(new[j1:j2])
            if with_symbols and names:
                shown = ", ".join(names[:6]) + (
                    f" and {len(names) - 6} more" if len(names) > 6 else ""
                )
                note += f" (functions {shown})"
            out.append(note + "]")
        else:
            out += numbered(new[j1:j2], j1 + 1)
    return "\n".join(out)


def build(case_no: int, kind: str, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(4100 + case_no)
    marker = f"MARK-{rng.randint(1000, 9999)}"
    marked = rng.choice([3, 4, 5, 30, 31, 32])  # far from the edited function
    old = module(rng, marker, marked)
    path = f"service_{rng.choice(WORDS)}_{case_no:02d}.py"
    edited = next(i for i, line in enumerate(old) if line.startswith("def ") and "_17(" in line)
    target = edited + 2  # the `base = ...` line of function 17
    old_line = old[target]
    new_lines = [old_line, "    base = round(base, 3)"]
    new = old[:target] + new_lines + old[target + 1 :]
    second = {
        "full": "\n".join(numbered(new)),
        "reference": by_reference(old, new, False),
        "reference_symbols": by_reference(old, new, True),
    }[kind]
    function = old[edited].split("(")[0][4:]
    messages = [
        {"role": "user", "content": f"Look at {path}."},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": READ_1, "name": "Read", "input": {"file_path": path}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": READ_1, "content": "\n".join(numbered(old))}
            ],
        },
        {"role": "assistant", "content": "I have read it."},
        {
            "role": "user",
            "content": f"In {function}, round base to 3 decimals right after it is computed.",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": EDIT,
                    "name": "Edit",
                    "input": {
                        "file_path": path,
                        "old_string": old_line,
                        "new_string": "\n".join(new_lines),
                    },
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": EDIT,
                    "content": "The file has been updated.",
                }
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": READ_2, "name": "Read", "input": {"file_path": path}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": READ_2, "content": second}],
        },
        {"role": "assistant", "content": "The change is in place."},
        {
            "role": "user",
            "content": f"Now, in {path}, change the line with {marker} so that the timeout is 90. "
            "Use the Edit tool directly.",
        },
    ]
    current = "\n".join(new)
    marker_line = next(line for line in new if marker in line)
    return {"model": model, "max_tokens": 1024, "tools": TOOLS, "messages": messages}, {
        "path": path,
        "current": current,
        "marker_line": marker_line,
    }


def outcome(body: dict[str, Any], truth: dict[str, Any]) -> str:
    if body.get("stop_reason") == "refusal":
        return "refusal"
    calls = [
        (b.get("name"), b.get("input") or {})
        for b in body.get("content", [])
        if b.get("type") == "tool_use"
    ]
    for name, args in calls:
        if name == "Edit" and args.get("file_path") == truth["path"]:
            anchor = str(args.get("old_string", ""))
            if (
                anchor
                and truth["current"].count(anchor) == 1
                and truth["marker_line"].strip() in anchor
            ):
                return "pass"
            return "bad_anchor"
        if name == "Read":
            return "reread"
    return "other"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-key-env", required=True)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--cases", type=int, default=10)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "e10e_result.json"))
    args = parser.parse_args(argv)
    key = os.environ.get(args.api_key_env, "")
    if not key:
        print(f"error: environment variable {args.api_key_env} is empty", file=sys.stderr)
        return 2
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    rows: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for repetition in range(args.repetitions):
            for case_no in range(1, args.cases + 1):
                for kind in VARIANTS:
                    request, truth = build(case_no, kind, args.model)
                    response = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=request,
                        timeout=120,
                    )
                    row: dict[str, Any] = {
                        "case": case_no,
                        "variant": kind,
                        "repetition": repetition + 1,
                        "status": response.status_code,
                    }
                    try:
                        body = response.json()
                    except ValueError:
                        body = {}
                    if response.status_code >= 400:
                        row["outcome"] = "http_error"
                        row["error_type"] = (
                            (body.get("error") or {}).get("type")
                            if isinstance(body, dict)
                            else None
                        )
                    else:
                        row["outcome"] = outcome(body, truth)
                        row["stop_reason"] = body.get("stop_reason")
                        row["input_tokens"] = (body.get("usage") or {}).get("input_tokens")
                    rows.append(row)
                    print(
                        json.dumps(
                            {
                                k: row.get(k)
                                for k in (
                                    "case",
                                    "variant",
                                    "repetition",
                                    "outcome",
                                    "input_tokens",
                                )
                            }
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
