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


def main() -> None:
    import yaml

    for family, make, seed in (
        ("json_fact_lookup", fact_case, 2501),
        ("json_verbatim_quote", quote_case, 2502),
        ("reference_fact_lookup", reference_fact_case, 2503),
        ("reference_verbatim_quote", reference_quote_case, 2504),
    ):
        rng = random.Random(seed)
        folder = ROOT / family
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, CASES_PER_FAMILY + 1):
            case = make(rng, n)
            text = yaml.safe_dump(case, sort_keys=False, allow_unicode=False, width=100)
            (folder / f"{n:02d}.yaml").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {4 * CASES_PER_FAMILY} cases to {ROOT}")


if __name__ == "__main__":
    main()
