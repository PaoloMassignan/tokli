"""Writes the smoke-tier case files (SPEC 012 QE-013). Run once; the output is committed and
reviewed. Not part of the package.

Usage: ``python evals/make_cases.py`` (from the repository root) or
``python <repo>/evals/make_cases.py``. The output is deterministic (fixed seed).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

CASE_SET = "2026-10-03.1"
CASES_PER_FAMILY = 22  # smoke_min_cases is 20; two spare
ROOT = Path(__file__).resolve().parent / "cases"

TOOLS = {
    "list_inventory": "Lists the items of a synthetic warehouse inventory.",
    "list_orders": "Lists synthetic customer orders.",
    "list_builds": "Lists recent synthetic CI builds.",
}
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
    "maple",
    "nimbus",
    "onyx",
    "pebble",
    "quartz",
    "raven",
]


def item(rng: random.Random, tool: str, i: int) -> dict[str, Any]:
    if tool == "list_inventory":
        return {
            "id": 1000 + i,
            "sku": f"SKU-{rng.randint(10000, 99999)}",
            "name": f"{rng.choice(WORDS)} {rng.choice(WORDS)}",
            "quantity": rng.randint(0, 500),
            "price": f"{rng.randint(1, 900)}.{rng.randint(0, 99):02d}",
            "tags": rng.sample(WORDS, rng.randint(0, 3)),
            "location": {"aisle": rng.randint(1, 40), "shelf": rng.choice("ABCDEF")},
        }
    if tool == "list_orders":
        return {
            "id": 5000 + i,
            "customer": f"customer-{rng.randint(100, 999)}",
            "status": rng.choice(["open", "shipped", "cancelled", "returned"]),
            "total": f"{rng.randint(5, 4000)}.{rng.randint(0, 99):02d}",
            "lines": [
                {"sku": f"SKU-{rng.randint(10000, 99999)}", "qty": rng.randint(1, 9)}
                for _ in range(rng.randint(1, 3))
            ],
        }
    return {
        "id": 200 + i,
        "branch": f"feature/{rng.choice(WORDS)}-{rng.randint(1, 99)}",
        "commit": f"{rng.getrandbits(28):07x}",
        "duration_s": rng.randint(30, 1800),
        "result": rng.choice(["success", "failure", "cancelled"]),
        "tests": {"passed": rng.randint(50, 900), "failed": rng.randint(0, 12)},
    }


def request(tool: str, payload: dict[str, Any], question: str) -> dict[str, Any]:
    call_id = "toolu_01SMOKECASE"
    return {
        "max_tokens": 400,
        "tools": [
            {
                "name": tool,
                "description": TOOLS[tool],
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        "messages": [
            {"role": "user", "content": f"Use the {tool} tool, then answer my question."},
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call_id, "name": tool, "input": {}}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": json.dumps(payload, indent=2),
                    },
                    {"type": "text", "text": question},
                ],
            },
        ],
    }


FACT_FIELDS = {
    "list_inventory": [("sku", "SKU"), ("quantity", "quantity"), ("price", "price")],
    "list_orders": [("total", "total"), ("customer", "customer")],
    "list_builds": [("commit", "commit"), ("duration_s", "duration in seconds")],
}


def fact_case(rng: random.Random, n: int) -> dict[str, Any]:
    tool = rng.choice(sorted(TOOLS))
    items = [item(rng, tool, i) for i in range(rng.randint(12, 25))]
    target = rng.choice(items)
    field, label = rng.choice(FACT_FIELDS[tool])
    question = (
        f"In the {tool} result, what is the {label} of the entry with id {target['id']}? "
        "Answer with only the value, nothing else."
    )
    return {
        "case_set": CASE_SET,
        "family": "json_fact_lookup",
        "assumption": "reads_minified_json",
        "checker": "exact_value",
        "request": request(tool, {"items": items, "count": len(items)}, question),
        "expected": str(target[field]),
    }


def quote_case(rng: random.Random, n: int) -> dict[str, Any]:
    tool = rng.choice(sorted(TOOLS))
    items = [item(rng, tool, i) for i in range(rng.randint(10, 20))]
    target = rng.choice(items)
    question = (
        f"Copy the complete JSON object of the entry with id {target['id']} from the {tool} "
        "result, exactly as it appears, so I can pass it to another tool. Reply with the JSON "
        "object only."
    )
    return {
        "case_set": CASE_SET,
        "family": "json_verbatim_quote",
        "assumption": "not_quoted_verbatim",
        "checker": "json_structural",
        "request": request(tool, {"items": items}, question),
        "expected": json.dumps(target, sort_keys=True),
    }


# -- reference families (S4, E11): the same file read twice; the later read is stubbed --------

SECTIONS = ["server", "cache", "retry", "logging", "storage", "queue"]
FIELDS = ["timeout_ms", "max_items", "label", "endpoint", "batch_size", "window_s", "token_ttl"]


def source_file(rng: random.Random) -> tuple[str, list[tuple[str, str, str]]]:
    """A synthetic Python settings module; returns (text, [(key, value, full line)])."""
    lines = ['"""Synthetic settings module."""', "", "from dataclasses import dataclass", ""]
    entries: list[tuple[str, str, str]] = []
    for section in rng.sample(SECTIONS, 4):
        lines += ["", "@dataclass", f"class {section.capitalize()}Settings:"]
        for name in rng.sample(FIELDS, 4):
            key = f"{section}_{name}"
            if name in ("label", "endpoint"):
                value = f"{rng.choice(WORDS)}-{rng.randint(10, 999)}"
                line = f'    {key}: str = "{value}"'
            else:
                value = str(rng.randint(2, 90000))
                line = f"    {key}: int = {value}"
            lines.append(line)
            entries.append((key, value, line))
    return "\n".join(lines) + "\n", entries


def numbered(text: str) -> str:
    """The text as a file-reading tool shows it: a line-number prefix on every line."""
    return "".join(f"{n:>6}\t{line}\n" for n, line in enumerate(text.split("\n")[:-1], 1))


def listing(rng: random.Random) -> str:
    names = sorted({f"{rng.choice(WORDS)}_{rng.randint(1, 99)}.py" for _ in range(12)})
    return "\n".join(f"src/app/{name}" for name in names) + "\n"


def reread_request(rng: random.Random, question: str, content: str) -> dict[str, Any]:
    path = f"src/app/{rng.choice(WORDS)}_settings.py"
    first, middle, again = "toolu_01SMOKEREF1", "toolu_01SMOKEREF2", "toolu_01SMOKEREF3"
    read = {
        "name": "Read",
        "description": "Reads a file.",
        "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}},
    }
    glob = {
        "name": "Glob",
        "description": "Lists files.",
        "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}},
    }
    shown = numbered(content)
    return {
        "max_tokens": 400,
        "tools": [read, glob],
        "messages": [
            {"role": "user", "content": f"Look at {path} and then answer my question."},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": first, "name": "Read", "input": {"file_path": path}}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": first, "content": shown}],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me also see the other files in that folder."},
                    {
                        "type": "tool_use",
                        "id": middle,
                        "name": "Glob",
                        "input": {"pattern": "src/app/*.py"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": middle, "content": listing(rng)}
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"I will read {path} again to be sure it is current."},
                    {"type": "tool_use", "id": again, "name": "Read", "input": {"file_path": path}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": again, "content": shown},
                    {"type": "text", "text": question.format(path=path)},
                ],
            },
        ],
    }


def reference_fact_case(rng: random.Random, n: int) -> dict[str, Any]:
    content, entries = source_file(rng)
    key, value, _ = rng.choice(entries)
    question = (
        "According to the latest read of {path}, what is the value of " + key + "? "
        "Answer with only the value, without quotes, nothing else."
    )
    return {
        "case_set": CASE_SET,
        "family": "reference_fact_lookup",
        "assumption": "resolves_result_reference",
        "checker": "exact_value",
        "request": reread_request(rng, question, content),
        "expected": value,
    }


def reference_quote_case(rng: random.Random, n: int) -> dict[str, Any]:
    content, entries = source_file(rng)
    key, _, line = rng.choice(entries)
    question = (
        "I want to change {path} with an exact-match edit. Give me the full line that contains "
        + key
        + " exactly as it appears in the file: keep its leading whitespace and leave out the "
        "line-number prefix of the read. Reply with that one line only."
    )
    return {
        "case_set": CASE_SET,
        "family": "reference_verbatim_quote",
        "assumption": "quotes_from_reference_target",
        "checker": "verbatim_line",
        "request": reread_request(rng, question, content),
        "expected": line,
    }


# -- grep and log families (S8a-1): content in a tool outside the default verbatim_tools ------

CASE_SET_S8A1 = "2026-10-03.2"
GREP_ROOTS = [
    "src/app",
    "lib/core",
    "C:\\work\\service\\src",
    "C:/work/tools",
    "\\\\build\\share\\repo",
]
GREP_FILES = ["config.py", "loader.py", "client.ts", "worker.go", "handler.cs", "schema.sql"]
SEPARATOR = {"C:\\work\\service\\src": "\\", "\\\\build\\share\\repo": "\\"}


def text_request(
    tool: str, description: str, args: dict[str, Any], content: str, question: str
) -> dict[str, Any]:
    call_id = "toolu_01SMOKECASE"
    return {
        "max_tokens": 400,
        "tools": [
            {
                "name": tool,
                "description": description,
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        "messages": [
            {"role": "user", "content": f"Use the {tool} tool, then answer my question."},
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call_id, "name": tool, "input": args}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call_id, "content": content},
                    {"type": "text", "text": question},
                ],
            },
        ],
    }


def grep_output(rng: random.Random) -> tuple[str, str, str, int, str]:
    """Search output over several files: (text, marker, path, line, content) of the marked
    match."""
    term = rng.choice(WORDS)
    marker = f"MARK-{rng.randint(1000, 9999)}"
    root = rng.choice(GREP_ROOTS)
    sep = SEPARATOR.get(root, "/")
    files = rng.sample(GREP_FILES, rng.randint(3, 5))
    matches: list[tuple[str, int, str]] = []
    for name in files:
        path = f"{root}{sep}{name}"
        line = rng.randint(1, 40)
        for _ in range(rng.randint(2, 5)):
            line += rng.randint(1, 30)
            indent = " " * rng.choice([0, 4, 8])
            matches.append(
                (path, line, f"{indent}{term}_{rng.choice(WORDS)} = {term}({rng.randint(1, 99)})")
            )
    target = rng.randrange(len(matches))
    path, line, content = matches[target]
    content = f"{content}  # {marker}"
    matches[target] = (path, line, content)
    text = f"Found {len(matches)} matches\n" + "".join(f"{p}:{n}:{c}\n" for p, n, c in matches)
    return text, marker, path, line, content


def grep_request(term_question: str, text: str) -> dict[str, Any]:
    return text_request(
        "Grep",
        "Searches the files of a synthetic repository for a pattern.",
        {"pattern": "match"},
        text,
        term_question,
    )


def grep_fact_case(rng: random.Random, n: int) -> dict[str, Any]:
    text, marker, path, line, _ = grep_output(rng)
    question = (
        f"In the Grep result, which file and line number contain the match with {marker}? "
        "Answer as <path>:<line> exactly as the result writes the path, nothing else."
    )
    return {
        "case_set": CASE_SET_S8A1,
        "family": "grep_fact_lookup",
        "assumption": "reads_grouped_search",
        "checker": "exact_value",
        "request": grep_request(question, text),
        "expected": f"{path}:{line}",
    }


def grep_quote_case(rng: random.Random, n: int) -> dict[str, Any]:
    text, marker, _, _, content = grep_output(rng)
    question = (
        f"I want to edit the line that contains {marker} with an exact-match edit. Give me that "
        "line exactly as it appears in the file: without the path and line-number prefix of the "
        "search result, keeping its leading whitespace. Reply with that one line only."
    )
    return {
        "case_set": CASE_SET_S8A1,
        "family": "grep_verbatim_quote",
        "assumption": "not_quoted_verbatim",
        "checker": "verbatim_line",
        "request": grep_request(question, text),
        "expected": content,
    }


def service_log(rng: random.Random) -> tuple[str, str, str, str]:
    """A log with repeated routine lines and a few severe ones: (text, marker, code, error
    line)."""
    marker = f"MARK-{rng.randint(1000, 9999)}"
    code = f"E{rng.randint(100, 999)}"
    failed = rng.randint(2000, 2999)
    error_at = rng.randint(30, 70)
    warn_at = rng.randint(5, 25)
    lines: list[str] = []
    minute, second = 0, 0
    error_line = ""
    for i in range(rng.randint(80, 120)):
        second += rng.randint(0, 3)
        minute, second = minute + second // 60, second % 60
        stamp = f"2026-10-03 09:{minute:02d}:{second:02d}"
        if i == error_at:
            error_line = f"{stamp} ERROR request {failed} failed with code {code} ({marker})"
            lines.append(error_line)
        elif i == warn_at:
            lines.append(
                f"{stamp} WARN pool {rng.choice(WORDS)} at {rng.randint(80, 99)} % capacity"
            )
        elif i % 4 == 0:
            lines.append(
                f"{stamp} DEBUG poll queue={rng.randint(0, 9)} lag={rng.randint(1, 900)}ms"
            )
        else:
            lines.append(f"{stamp} INFO request {1000 + i} served in {rng.randint(3, 400)} ms")
    return "\n".join(lines) + "\n", marker, code, error_line


def log_request(question: str, text: str) -> dict[str, Any]:
    return text_request(
        "service_logs",
        "Returns the recent logs of a synthetic service.",
        {"service": "api"},
        text,
        question,
    )


def log_fact_case(rng: random.Random, n: int) -> dict[str, Any]:
    text, marker, code, _ = service_log(rng)
    question = (
        f"In the service_logs result, which error code did the failed request marked {marker} "
        "return? Answer with only the code, nothing else."
    )
    return {
        "case_set": CASE_SET_S8A1,
        "family": "log_fact_lookup",
        "assumption": "omitted_log_lines_not_needed",
        "checker": "exact_value",
        "request": log_request(question, text),
        "expected": code,
    }


def log_quote_case(rng: random.Random, n: int) -> dict[str, Any]:
    text, marker, _, error_line = service_log(rng)
    question = (
        f"Copy the full log line that contains {marker} exactly as it appears in the service_logs "
        "result, so I can search for it. Reply with that one line only."
    )
    return {
        "case_set": CASE_SET_S8A1,
        "family": "log_verbatim_quote",
        "assumption": "not_quoted_verbatim",
        "checker": "verbatim_line",
        "request": log_request(question, text),
        "expected": error_line,
    }


# -- reread family (S8c): old edit content is pruned at a resume; the agent should re-read ------

CASE_SET_S8C = "2026-10-04.2"
REREAD_TOOLS = [
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
SMALL_TALK = [
    ("What does HTTP 429 mean?", "Too Many Requests: the client is rate limited."),
    ("And 503?", "Service Unavailable."),
    ("Which port does HTTPS use by default?", "443."),
    ("Thanks. Let me think about the next step.", "Sure."),
    ("What is a semantic version?", "MAJOR.MINOR.PATCH."),
    ("OK.", "Anything else?"),
]


def reread_case(rng: random.Random, n: int) -> dict[str, Any]:
    name = f"{rng.choice(WORDS)}_{rng.choice(SECTIONS)}_settings.py"
    keys = rng.sample([f"{s.upper()}_{f.upper()}" for s in SECTIONS for f in FIELDS], 12)

    def value(key: str) -> str:  # realistic per key kind (the first run got refusals, S8c report)
        if key.endswith("ENDPOINT"):
            return f'"https://{rng.choice(WORDS)}.example.invalid/v{rng.randint(1, 9)}"'
        if key.endswith("LABEL"):
            return f'"{rng.choice(WORDS)}-{rng.choice(WORDS)}"'
        return str(rng.randint(2, 9999))

    values = {key: value(key) for key in keys}
    content = '"""Synthetic settings."""\n\n' + "".join(f"{key} = {values[key]}\n" for key in keys)
    asked = rng.choice(keys)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Create {name} with the settings we discussed."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01REREADW",
                    "name": "Write",
                    "input": {"file_path": name, "content": content},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_01REREADW",
                    "content": "File created.",
                }
            ],
        },
        {"role": "assistant", "content": f"Created {name}."},
    ]
    for question, answer in rng.sample(SMALL_TALK, 5):
        messages += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    messages.append(
        {
            "role": "user",
            "content": f"What is the value of {asked} in {name} right now? Reply with the value "
            "only, or read the file first if you are not sure.",
        }
    )
    return {
        "case_set": CASE_SET_S8C,
        "family": "reread_after_pruned_edit",
        "assumption": "edit_content_not_needed",
        "checker": "answer_or_read",
        "request": {"max_tokens": 1024, "tools": REREAD_TOOLS, "messages": messages},
        "expected": values[asked].strip('"'),
        "expected_read_path": name,
    }


# -- re-read families (S8e): read, edit one function, read again; then work on another function --

CASE_SET_S8E = "2026-10-04.3"
REREAD_EDIT_TOOLS = [tool for tool in REREAD_TOOLS if tool["name"] in ("Read", "Edit")]


def reread_module(rng: random.Random, marker: str, marked: int) -> tuple[list[str], dict[str, str]]:
    """A synthetic module of 36 functions; returns its lines and each function's default factor."""
    lines = ['"""Synthetic service module."""', "", "import math", ""]
    factors: dict[str, str] = {}
    for n in range(36):
        name = f"{rng.choice(WORDS)}_{n:02d}"
        factor = str(rng.randint(2, 99))
        factors[name] = factor
        lines += [
            f"def {name}(value, factor={factor}):",
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
    return lines, factors


def reread_history(rng: random.Random, n: int) -> dict[str, Any]:
    marker = f"MARK-{rng.randint(1000, 9999)}"
    marked = rng.choice([3, 4, 5, 30, 31, 32])  # far from the edited function (17)
    old, factors = reread_module(rng, marker, marked)
    path = f"service_{rng.choice(WORDS)}_{n:02d}.py"
    edited = next(i for i, line in enumerate(old) if line.startswith("def ") and "_17(" in line)
    target = edited + 2
    new = [*old[:target], old[target], "    base = round(base, 3)", *old[target + 1 :]]
    function = old[edited].split("(")[0][4:]
    numbered_old = "\n".join(f"{k:>6}\t{line}" for k, line in enumerate(old, start=1))
    numbered_new = "\n".join(f"{k:>6}\t{line}" for k, line in enumerate(new, start=1))
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Look at {path}."},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01REREAD1",
                    "name": "Read",
                    "input": {"file_path": path},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_01REREAD1", "content": numbered_old}
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
                    "id": "toolu_01REEDIT1",
                    "name": "Edit",
                    "input": {
                        "file_path": path,
                        "old_string": old[target],
                        "new_string": old[target] + "\n    base = round(base, 3)",
                    },
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_01REEDIT1",
                    "content": "The file has been updated.",
                }
            ],
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01REREAD2",
                    "name": "Read",
                    "input": {"file_path": path},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_01REREAD2", "content": numbered_new}
            ],
        },
        {"role": "assistant", "content": "The change is in place."},
    ]
    asked = rng.choice([name for name in factors if name.endswith(("_02", "_06", "_28", "_33"))])
    return {
        "path": path,
        "messages": messages,
        "marker": marker,
        "marker_line": next(line for line in new if marker in line),
        "current": "\n".join(new) + "\n",
        "asked": asked,
        "factor": factors[asked],
    }


def reread_fact_case(rng: random.Random, n: int) -> dict[str, Any]:
    history = reread_history(rng, n)
    question = (
        f"In {history['path']}, what is the default value of factor in {history['asked']}? "
        "Reply with the number only."
    )
    return {
        "case_set": CASE_SET_S8E,
        "family": "reread_fact_lookup",
        "assumption": "reads_partial_reference",
        "checker": "answer_or_read",
        "request": {
            "max_tokens": 1024,
            "tools": REREAD_EDIT_TOOLS,
            "messages": [*history["messages"], {"role": "user", "content": question}],
        },
        "expected": history["factor"],
        "expected_read_path": history["path"],
    }


def reread_edit_case(rng: random.Random, n: int) -> dict[str, Any]:
    history = reread_history(rng, n)
    task = (
        f"Now, in {history['path']}, change the line with {history['marker']} so that the timeout "
        "is 90. Use the Edit tool directly."
    )
    return {
        "case_set": CASE_SET_S8E,
        "family": "reread_edit_anchor",
        "assumption": "quotes_from_reference_target",
        "checker": "edit_anchor",
        "request": {
            "max_tokens": 1024,
            "tools": REREAD_EDIT_TOOLS,
            "messages": [*history["messages"], {"role": "user", "content": task}],
        },
        "expected": history["marker_line"],
        "expected_read_path": history["path"],
        "current_file": history["current"],
    }


def main() -> None:
    import yaml

    families = (
        ("json_fact_lookup", fact_case, 2501),
        ("json_verbatim_quote", quote_case, 2502),
        ("reference_fact_lookup", reference_fact_case, 2503),
        ("reference_verbatim_quote", reference_quote_case, 2504),
        ("grep_fact_lookup", grep_fact_case, 2505),
        ("grep_verbatim_quote", grep_quote_case, 2506),
        ("log_fact_lookup", log_fact_case, 2507),
        ("log_verbatim_quote", log_quote_case, 2508),
        ("reread_after_pruned_edit", reread_case, 2509),
        ("reread_fact_lookup", reread_fact_case, 2510),
        ("reread_edit_anchor", reread_edit_case, 2511),
    )
    for family, make, seed in families:
        rng = random.Random(seed)
        folder = ROOT / family
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, CASES_PER_FAMILY + 1):
            case = make(rng, n)
            text = yaml.safe_dump(case, sort_keys=False, allow_unicode=False, width=100)
            (folder / f"{n:02d}.yaml").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(families) * CASES_PER_FAMILY} cases to {ROOT}")


if __name__ == "__main__":
    main()
