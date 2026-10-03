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


def main() -> None:
    import yaml

    for family, make, seed in (
        ("json_fact_lookup", fact_case, 2501),
        ("json_verbatim_quote", quote_case, 2502),
    ):
        rng = random.Random(seed)
        folder = ROOT / family
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, CASES_PER_FAMILY + 1):
            case = make(rng, n)
            text = yaml.safe_dump(case, sort_keys=False, allow_unicode=False, width=100)
            (folder / f"{n:02d}.yaml").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {2 * CASES_PER_FAMILY} cases to {ROOT}")


if __name__ == "__main__":
    main()
