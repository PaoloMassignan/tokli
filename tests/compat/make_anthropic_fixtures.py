"""Generates the synthetic Anthropic Messages compat fixtures (TOKLI_TEST_STRATEGY §4).

Run from the repository root: ``python -m tests.compat.make_anthropic_fixtures``. The output files
are committed; this script documents how they were made. Content is invented and contains canary
strings (``TOKLI-CANARY-…``) for the leak scans. No real prompts, keys, users or paths.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "fixtures" / "anthropic_messages"

PRETTY_ISSUE = json.dumps(
    {
        "number": 42,
        "title": "Proxy drops header TOKLI-CANARY-JSON",
        "labels": [{"name": "bug", "color": "d73a4a"}, {"name": "proxy", "color": "0e8a16"}],
        "state": "open",
        "comments": 3,
        "score": 1.0,
        "ratio": 1e2,
    },
    indent=2,
)
PRETTY_LIST = json.dumps(
    [{"id": i, "name": f"item-{i}", "ok": i % 2 == 0, "note": "café"} for i in range(8)],
    indent=4,
    ensure_ascii=False,
)
FILE_CONTENT = (
    '     1\t{\n     2\t  "key": "value TOKLI-CANARY-FILE",\n     3\t  "n": 1\n     4\t}\n'
)
REMINDER = (
    "<system-reminder>\nThe user opened the file src/app.py in the IDE. TOKLI-CANARY-REMINDER\n"
    "</system-reminder>"
)

FIXTURES: dict[str, dict[str, object]] = {
    "string_content": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Say hello. TOKLI-CANARY-USER"}],
    },
    "system_string": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 256,
        "system": "You are terse. TOKLI-CANARY-SYSTEM",
        "messages": [{"role": "user", "content": "Hi"}],
    },
    "blocks_with_cache_control": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1024,
        "system": [
            {"type": "text", "text": "System prompt part one."},
            {"type": "text", "text": "Part two.", "cache_control": {"type": "ephemeral"}},
        ],
        "tools": [
            {
                "name": "get_issue",
                "description": "Fetch an issue. TOKLI-CANARY-TOOLDESC",
                "input_schema": {"type": "object", "properties": {"n": {"type": "integer"}}},
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "First block."},
                    {
                        "type": "text",
                        "text": "Second block.",
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
            }
        ],
    },
    "tool_use_and_results": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 2048,
        "stream": True,
        "tools": [
            {"name": "Read", "description": "Read a file", "input_schema": {"type": "object"}},
            {
                "name": "mcp__tracker__get_issue",
                "description": "Issue",
                "input_schema": {"type": "object"},
            },
        ],
        "messages": [
            {"role": "user", "content": "Look at issue 42 and the config file."},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Fetching both."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01A",
                        "name": "mcp__tracker__get_issue",
                        "input": {"n": 42},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_01B",
                        "name": "Read",
                        "input": {"file_path": "config.json"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_01A", "content": PRETTY_ISSUE},
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01B",
                        "content": [{"type": "text", "text": FILE_CONTENT}],
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01C",
                        "name": "mcp__tracker__get_issue",
                        "input": {"n": 7},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01C",
                        "is_error": True,
                        "content": [
                            {
                                "type": "text",
                                "text": PRETTY_LIST,
                                "cache_control": {"type": "ephemeral"},
                            },
                        ],
                    },
                    {"type": "tool_result", "tool_use_id": "toolu_UNKNOWN", "content": PRETTY_LIST},
                    {"type": "text", "text": "Now summarise."},
                ],
            },
        ],
    },
    "images_and_documents": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgo=",
                        },
                    },
                    {
                        "type": "document",
                        "source": {"type": "text", "media_type": "text/plain", "data": "doc text"},
                    },
                    {"type": "text", "text": "Describe both."},
                ],
            }
        ],
    },
    "thinking_and_signatures": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 4096,
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "messages": [
            {"role": "user", "content": "Plan the change."},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Reasoning text TOKLI-CANARY-THINK",
                        "signature": "c2lnbmF0dXJl",
                    },
                    {"type": "redacted_thinking", "data": "ZW5jcnlwdGVk"},
                    {"type": "text", "text": "Here is the plan."},
                ],
            },
            {"role": "user", "content": "Continue."},
        ],
    },
    "server_tool_blocks": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Search the web."},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "server_tool_use",
                        "id": "srvtoolu_1",
                        "name": "web_search",
                        "input": {"query": "tokli"},
                    },
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_1",
                        "content": [
                            {
                                "type": "web_search_result",
                                "url": "https://example.invalid",
                                "title": "T",
                            }
                        ],
                    },
                ],
            },
            {"role": "user", "content": "Thanks."},
        ],
    },
    "unknown_future_parts": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 128,
        "x_future": {"flag": True, "values": [1, 2.5, "three"]},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "future_block", "payload": {"text": "not a segment"}},
                    {"type": "text", "text": "Known block."},
                ],
            }
        ],
    },
    "claude_code_like": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 32000,
        "stream": True,
        "metadata": {"user_id": "user_0000"},
        "system": [
            {
                "type": "text",
                "text": "You are an interactive CLI agent.",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "tools": [
            {"name": "Bash", "description": "Run a command", "input_schema": {"type": "object"}},
            {
                "name": "mcp__api__list_items",
                "description": "List items",
                "input_schema": {"type": "object"},
            },
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": REMINDER},
                    {"type": "text", "text": "List the items and check the build."},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_02A",
                        "name": "mcp__api__list_items",
                        "input": {},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_02B",
                        "name": "Bash",
                        "input": {"command": "cat items.json"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_02A",
                        "content": PRETTY_LIST + "\n" + REMINDER,
                    },
                    {"type": "tool_result", "tool_use_id": "toolu_02B", "content": PRETTY_LIST},
                    {"type": "text", "text": REMINDER, "cache_control": {"type": "ephemeral"}},
                ],
            },
        ],
    },
    "unicode_and_numbers": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 64,
        "temperature": 0.7,
        "top_p": 1e-1,
        "messages": [
            {"role": "user", "content": "Café — 漢字 \U0001f600 TOKLI-CANARY-UNICODE"},
        ],
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in FIXTURES.items():
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (OUT / f"{name}.json").write_bytes(raw)
    print(f"wrote {len(FIXTURES)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
