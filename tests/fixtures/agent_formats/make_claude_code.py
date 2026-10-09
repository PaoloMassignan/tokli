"""Builds `claude_code.json`: synthetic content in the real shapes of Claude Code traffic (S8h P2).

The shapes were measured on the human's own sessions, with consent, as counters and patterns
only (2026-10-09, 21 days); no real line was read into this file:
- `Read` input `{file_path}` or `{file_path, offset, limit}`; its result is a string numbered
  `"{n}\\t<content>"` with no padding (1,684 of 1,684 numbered results). It sometimes ends with an
  appended `<system-reminder>` block (89 of 1,837).
- `Edit` input `{file_path, old_string, new_string, replace_all}`; `Write` input
  `{file_path, content}`. Their results are short strings.
- `Bash` input `{command, description}` (sometimes `timeout`, `run_in_background`); string result.
- `Grep` input `{pattern, path, output_mode, -n}`; string result, `path:line:content` lines.
- MCP tools (`mcp__<server>__<tool>`): the result is a list of `text` blocks.

Run `python tests/fixtures/agent_formats/make_claude_code.py` to rebuild the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT_DIR = "C:\\work\\demo"  # a synthetic Windows working directory
MODULE = ROOT_DIR + "\\src\\module.py"
NEW_FILE = ROOT_DIR + "\\src\\helpers.py"
REMINDER = "<system-reminder>\nA synthetic reminder about the session.\n</system-reminder>"


def numbered(lines: list[str], first: int = 1) -> str:
    """Claude Code's `Read` numbering: `"{n}\\t"`, no padding."""
    return "\n".join(f"{n}\t{line}" for n, line in enumerate(lines, start=first))


def call(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}],
    }


def result(call_id: str, content: Any) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": call_id, "content": content}],
    }


def build() -> dict[str, Any]:
    module = [f"def synthetic_function_{n}(value):  # demo line {n}" for n in range(1, 41)]
    edited = [
        *module[:20],
        "def synthetic_function_21(value):  # demo line 21, edited",
        *module[21:],
    ]
    helpers = [f"HELPER_{n} = {n} * 7  # synthetic helper constant" for n in range(1, 31)]
    listing = json.dumps(
        {"items": [{"id": n, "name": f"item-{n}", "tags": ["alpha", "beta"]} for n in range(12)]},
        indent=2,
    )
    grep = "\n".join(  # ripgrep groups the matches by file
        f"src/module_{f}.py:{10 + n}:    value = compute_{n}(value)"
        for f in range(3)
        for n in range(6)
    )
    log = "\n".join(
        f"2026-10-09 10:00:{n:02d} {'DEBUG' if n % 4 else 'INFO'} worker {n % 3} step {n} done"
        for n in range(40)
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Start the synthetic task."}]
    messages += [
        call("toolu_01", "Read", {"file_path": MODULE}),
        result("toolu_01", numbered(module) + "\n\n" + REMINDER),
        call(
            "toolu_02",
            "Edit",
            {
                "file_path": MODULE,
                "old_string": module[20],
                "new_string": edited[20],
                "replace_all": False,
            },
        ),
        result("toolu_02", f"The file {MODULE} has been updated successfully."),
        call("toolu_03", "Read", {"file_path": MODULE}),
        result("toolu_03", numbered(edited)),
        call("toolu_04", "mcp__demo__list_items", {}),
        result("toolu_04", [{"type": "text", "text": listing}]),
        call(
            "toolu_05",
            "Grep",
            {"pattern": "compute_", "path": ROOT_DIR, "output_mode": "content", "-n": True},
        ),
        result("toolu_05", grep),
        call(
            "toolu_06", "Bash", {"command": "python run_worker.py", "description": "Run the worker"}
        ),
        result("toolu_06", log),
        call("toolu_07", "Write", {"file_path": NEW_FILE, "content": "\n".join(helpers) + "\n"}),
        result("toolu_07", f"File created successfully at: {NEW_FILE}"),
        call("toolu_08", "Read", {"file_path": NEW_FILE}),
        result("toolu_08", numbered(helpers)),
        call("toolu_09", "mcp__demo__list_items", {}),
        result("toolu_09", [{"type": "text", "text": listing}]),
        {"role": "user", "content": "What should change next?"},
    ]
    return {"model": "claude-opus-5-5", "max_tokens": 1024, "stream": True, "messages": messages}


if __name__ == "__main__":
    target = HERE / "claude_code.json"
    target.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target.name}")
