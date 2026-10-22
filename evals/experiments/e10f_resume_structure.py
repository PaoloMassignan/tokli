"""E10(f): does the *structure* of an old shell read, or a stub of an old script, draw refusals?

E10(d) showed that replacing an old tool result with a stub makes the provider refuse in 65-80 %
of calls, even when the stub says to read the file again. This experiment tests forms that keep
part of the information, for the three largest shell targets of the developer's traffic
(TOKLI_EVIDENCE, S8i follow-up, 2026-10-17):

- `code`: the agent read a Python module with `cat` through `Bash`. Forms:
  - `original` (control);
  - `structure`: declarations kept; each omitted body becomes
    `[tokli: lines <a>-<b> omitted — run the command again for them]`;
  - `stub`: the E10(d) hint stub, as a reproduction.
  Three questions per module:
  - `signature`: answerable from the structure;
  - `body`: a value inside a function body;
  - `edit`: change a value inside a body (records blind writes and edits whose `old_string` is
    not in the file).
- `doc`: the agent read a Markdown spec with `sed -n`. Forms: `original`, `structure` (headings
  kept, sections omitted with a note), `stub`. Questions: `heading` (answerable from the
  structure) and `body` (a default value inside a section).
- `script`: the agent ran a long Python script through a `Bash` heredoc; its output is intact.
  Forms: `original` and `stub` (the command text becomes
  `[tokli: earlier command text omitted (<n> tokens); its output follows]`). Question: `output`
  (a number printed by the script).

Everything is synthetic and generated here with a fixed seed. Per call it records the HTTP
status, `stop_reason` and the outcome:
- `answer`: the right answer;
- `reread`: the agent runs the read again (Bash with the file name, or Read of it);
- `edit_ok`: an Edit whose `old_string` is in the file and whose `new_string` has the new value;
- `edit_bad`: an Edit whose `old_string` is not in the file;
- `blind_write`: a Write of the file without reading it again;
- `fail`, `refusal`, `empty`, `http_error`.

Decision rule, fixed before the run (as E10(d)), per family:
- **go** for `structure` (code, doc) if its refusals are at most the control's plus 1, and it
  has no more `fail`, `edit_bad` or `blind_write` than the control. `answer`, `reread` and
  `edit_ok` all count as correct behaviour;
- **go** for the script `stub` on the same terms, against `original`;
- otherwise that form stops, and the result goes into TOKLI_EVIDENCE.
The `stub` forms of code and doc reproduce E10(d): many refusals are expected there.

The API key is read only from the environment variable named by `--api-key-env`; it is never
printed or written. `--dry-run` sends nothing: it prints the number of calls and an estimate of
their cost.

Usage:
    python evals/experiments/e10f_resume_structure.py --dry-run
    python evals/experiments/e10f_resume_structure.py --api-key-env NAME [--model ID]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED = 20261017
CASES_PER_FAMILY = 5
FORMS = {
    "code": ("original", "structure", "stub"),
    "doc": ("original", "structure", "stub"),
    "script": ("original", "stub"),
}
QUESTIONS = {
    "code": ("signature", "body", "edit"),
    "doc": ("heading", "body"),
    "script": ("output",),
}
PRICE_IN, PRICE_OUT = 4.0, 20.0  # claude-opus-5-5, USD per MTok (shipped price book)

SYSTEM = (
    "You are a coding agent working in a repository. Use the tools to read and change files. "
    "Answer briefly."
)
TOOLS = [
    {
        "name": "Bash",
        "description": "Runs a shell command and returns its output.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
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
        "name": "Write",
        "description": "Writes a whole file.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        },
    },
]
SMALL_TALK = [
    ("What does HTTP 429 mean?", "Too Many Requests: the client is rate limited."),
    ("Which port does HTTPS use by default?", "443."),
    ("What is a semantic version?", "MAJOR.MINOR.PATCH."),
    ("And 503?", "Service Unavailable."),
    ("Thanks. Let me think about the next step.", "Sure."),
]
WORDS = [
    "harbor",
    "quartz",
    "lumen",
    "fjord",
    "birch",
    "amber",
    "cobalt",
    "delta",
    "ember",
    "flint",
    "garnet",
    "heron",
    "iris",
    "juniper",
    "kestrel",
    "lagoon",
    "maple",
    "nimbus",
]
NOTE = "[tokli: lines {a}-{b} omitted — run the command again for them]"


@dataclass(frozen=True)
class Case:
    family: str
    case_id: str
    path: str
    command: str
    original: str  # the tool result (code, doc) or the command text (script)
    output: str  # script output (script family)
    answers: dict[str, Any]


# -- synthetic material ---------------------------------------------------------------------


def _name(rng: random.Random, n: int = 2) -> str:
    return "_".join(rng.sample(WORDS, n))


def make_code(rng: random.Random, index: int) -> Case:
    module = _name(rng)
    path = f"src/{module}.py"
    lines = [
        f'"""Synthetic module {module}."""',
        "",
        "from __future__ import annotations",
        "",
        "import logging",
        "",
        "LOG = logging.getLogger(__name__)",
        "",
    ]
    functions = []
    for f in range(6):
        fname = f"{rng.choice(['load', 'merge', 'score', 'render', 'check', 'flush'])}_{_name(rng)}"
        params = [_name(rng, 1) + f"_{p}" for p in range(rng.randint(2, 4))]
        local = f"{rng.choice(['limit', 'window', 'budget', 'retries', 'margin'])}_{f}"
        value = rng.randint(100, 9999)
        functions.append((fname, params, local, value))
        lines += [
            "",
            f"def {fname}({', '.join(p + ': int' for p in params)}) -> int:",
            f'    """Synthetic function {f}."""',
            f"    {local} = {value}",
            "    total = 0",
        ]
        for p in params:
            lines += [
                f"    if {p} > {local}:",
                f"        LOG.debug('clamp {p}')",
                f"        {p} = {local}",
                f"    total += {p}",
            ]
        lines += [
            "    for step in range(3):",
            "        total += step * 2",
            f"    return total % {local}",
        ]
    text = "\n".join(lines) + "\n"
    sig, body, edit = functions[1], functions[3], functions[4]
    return Case(
        "code",
        f"code{index}",
        path,
        f"cat {path}",
        text,
        "",
        {
            "signature": {"function": sig[0], "expect_all": sig[1]},
            "body": {"function": body[0], "local": body[2], "expect": str(body[3])},
            "edit": {"function": edit[0], "local": edit[2], "old": edit[3], "new": edit[3] + 1},
        },
    )


def make_doc(rng: random.Random, index: int) -> Case:
    title = _name(rng).replace("_", " ").title()
    path = f"docs/{_name(rng)}.md"
    lines = [f"# SPEC — {title}", "", "Status: Draft", ""]
    headings, keys = [], []
    for s in range(1, 7):
        heading = (
            f"{rng.choice(['Purpose', 'Settings', 'Limits', 'Errors', 'Storage', 'Rules'])} "
            f"of the {rng.choice(WORDS)} stage"
        )
        headings.append(heading)
        lines += [f"## {s}. {heading}", ""]
        for r in range(4):
            lines.append(
                f"The {rng.choice(WORDS)} step handles case {s}.{r} as described here, "
                f"and records it in the trace."
            )
        lines += ["", "| Key | Default |", "|---|---|"]
        for _ in range(4):
            key = f"{rng.choice(WORDS)}.{rng.choice(WORDS)}_{rng.randint(1, 99)}"
            default = rng.randint(10, 99999)
            keys.append((key, default))
            lines.append(f"| `{key}` | {default} |")
        lines.append("")
    text = "\n".join(lines) + "\n"
    k = rng.randrange(len(keys))
    return Case(
        "doc",
        f"doc{index}",
        path,
        f"sed -n 1,400p {path}",
        text,
        "",
        {
            "heading": {"section": 4, "expect": headings[3]},
            "body": {"key": keys[k][0], "expect": str(keys[k][1])},
        },
    )


def make_script(rng: random.Random, index: int) -> Case:
    threshold = rng.randint(20, 60)
    data = [rng.randint(1, 100) for _ in range(60)]
    kept = [x for x in data if x > threshold]
    body = [
        "python - <<'EOF'",
        '"""Synthetic analysis: keep values above a threshold."""',
        "import statistics",
        "",
        f"THRESHOLD = {threshold}",
        f"DATA = {data}",
        "",
        "",
        "def keep(values, limit):",
        '    """Values strictly above the limit."""',
        "    out = []",
        "    for value in values:",
        "        if value > limit:",
        "            out.append(value)",
        "    return out",
        "",
        "",
        "def describe(values):",
        '    """Count, mean and spread."""',
        "    if not values:",
        "        return 0, 0.0, 0.0",
        "    mean = statistics.mean(values)",
        "    spread = statistics.pstdev(values)",
        "    return len(values), round(mean, 2), round(spread, 2)",
        "",
        "",
        "count, mean, spread = describe(keep(DATA, THRESHOLD))",
        'print(f"kept {count}")',
        'print(f"mean {mean}")',
        'print(f"spread {spread}")',
        "EOF",
    ]
    import statistics

    output = (
        f"kept {len(kept)}\nmean {round(statistics.mean(kept), 2)}\n"
        f"spread {round(statistics.pstdev(kept), 2)}\n"
    )
    return Case(
        "script",
        f"script{index}",
        "",
        "\n".join(body),
        "\n".join(body),
        output,
        {"output": {"expect": str(len(kept))}},
    )


def cases() -> list[Case]:
    rng = random.Random(SEED)
    out: list[Case] = []
    for i in range(CASES_PER_FAMILY):
        out += [make_code(rng, i), make_doc(rng, i), make_script(rng, i)]
    return out


# -- forms ----------------------------------------------------------------------------------


def _structure(text: str, keep: list[bool]) -> str:
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if keep[i]:
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and not keep[j]:
            j += 1
        if j - i >= 3:
            indent = re.match(r"\s*", lines[i]).group(0)  # type: ignore[union-attr]
            out.append(indent + NOTE.format(a=i + 1, b=j))
        else:
            out.extend(lines[i:j])
        i = j
    return "\n".join(out) + "\n"


def code_structure(text: str) -> str:
    keep = [
        i < 8
        or bool(re.match(r"\s*(@|def |class |async def )", line))
        or (line[:1] not in (" ", "\t") and line.strip() != "")
        for i, line in enumerate(text.splitlines())
    ]
    return _structure(text, keep)


def doc_structure(text: str) -> str:
    keep = [i < 4 or line.startswith("#") for i, line in enumerate(text.splitlines())]
    return _structure(text, keep)


def stub(text: str) -> str:
    return (
        f"[tokli: earlier tool output omitted ({max(1, len(text) // 4)} tokens) — "
        "read the file again if you need it]"
    )


def form_of(case: Case, form: str) -> tuple[str, str]:
    """(command shown in the old tool call, tool result) for the form."""
    if case.family == "script":
        if form == "stub":
            n = max(1, len(case.original) // 4)
            return (
                f"[tokli: earlier command text omitted ({n} tokens); its output follows]",
                case.output,
            )
        return case.command, case.output
    if form == "original":
        return case.command, case.original
    if form == "stub":
        return case.command, stub(case.original)
    return case.command, (code_structure if case.family == "code" else doc_structure)(case.original)


def question(case: Case, kind: str) -> str:
    a = case.answers[kind]
    if kind == "signature":
        return (
            f"Which parameters does `{a['function']}` in {case.path} take? "
            "Answer with the parameter names only."
        )
    if kind == "body" and case.family == "code":
        return f"Inside `{a['function']}` in {case.path}, what value is assigned to `{a['local']}`?"
    if kind == "edit":
        return (
            f"In {case.path}, inside `{a['function']}`, change the value assigned to "
            f"`{a['local']}` from {a['old']} to {a['new']}."
        )
    if kind == "heading":
        return f"What is the heading of section {a['section']} of {case.path}?"
    if kind == "body":
        return f"According to {case.path}, what is the default of `{a['key']}`?"
    return "How many values did the analysis you ran keep?"


def request(case: Case, form: str, kind: str, model: str) -> dict[str, Any]:
    command, result = form_of(case, form)
    ask = (
        f"Show me {case.path}."
        if case.family != "script"
        else "Run the threshold analysis on the sample data."
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": ask},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01E10F",
                    "name": "Bash",
                    "input": {"command": command},
                }
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_01E10F", "content": result}],
        },
        {"role": "assistant", "content": "Done."},
    ]
    for user, assistant in SMALL_TALK:
        messages += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
    messages.append({"role": "user", "content": question(case, kind)})
    return {
        "model": model,
        "max_tokens": 1024,
        "system": SYSTEM,
        "tools": TOOLS,
        "messages": messages,
    }


# -- outcome --------------------------------------------------------------------------------


def outcome(body: dict[str, Any], case: Case, kind: str) -> str:
    if body.get("stop_reason") == "refusal":
        return "refusal"
    blocks = body.get("content", [])
    calls = [(b.get("name"), b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
    text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    name = Path(case.path).name if case.path else None
    for tool, args in calls:
        if name and tool == "Bash" and name in str(args.get("command", "")):
            return "reread"
        if name and tool == "Read" and str(args.get("file_path", "")).endswith(name):
            return "reread"
    a = case.answers[kind]
    if kind == "edit":
        for tool, args in calls:
            if tool == "Edit" and str(args.get("file_path", "")).endswith(name or ""):
                old, new = str(args.get("old_string", "")), str(args.get("new_string", ""))
                return (
                    "edit_ok"
                    if old and old in case.original and str(a["new"]) in new
                    else "edit_bad"
                )
            if tool == "Write" and str(args.get("file_path", "")).endswith(name or ""):
                return "blind_write"
        return "fail" if text.strip() or calls else "empty"
    if kind == "signature":
        ok = all(p in text for p in a["expect_all"])
    else:
        ok = a["expect"].lower() in text.lower()
    if ok:
        return "answer"
    return "fail" if text.strip() or calls else "empty"


# -- run ------------------------------------------------------------------------------------


def plan(repetitions: int) -> list[tuple[int, Case, str, str]]:
    return [
        (r, c, form, kind)
        for r in range(repetitions)
        for c in cases()
        for form in FORMS[c.family]
        for kind in QUESTIONS[c.family]
    ]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-key-env")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="send nothing; print the plan")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "e10f_result.json"))
    args = parser.parse_args(argv)
    calls = plan(args.repetitions)
    if args.dry_run:
        per = collections.Counter((c.family, form) for _, c, form, _ in calls)
        chars = sum(len(json.dumps(request(c, f, k, args.model))) for _, c, f, k in calls)
        est = chars / 4 / 1e6 * PRICE_IN + len(calls) * 300 / 1e6 * PRICE_OUT
        for (family, form), n in sorted(per.items()):
            print(f"{family:<7}{form:<10}{n:>4} calls")
        print(
            f"total {len(calls)} calls, about {chars / 4:,.0f} input tokens; "
            f"estimated cost ${est:.2f} on {args.model} (no cache)"
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
    rows: list[dict[str, Any]] = []
    with httpx.Client() as client:
        for repetition, case, form, kind in calls:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=request(case, form, kind, args.model),
                timeout=120,
            )
            row: dict[str, Any] = {
                "case": case.case_id,
                "family": case.family,
                "form": form,
                "question": kind,
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
                row.update(
                    outcome=outcome(body, case, kind),
                    stop_reason=body.get("stop_reason"),
                    input_tokens=body.get("usage", {}).get("input_tokens"),
                )
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("case", "form", "question", "outcome")}))
    summary: dict[str, dict[str, int]] = collections.defaultdict(dict)
    grouped = collections.Counter(
        (r["family"], r["form"], r["question"], r["outcome"]) for r in rows
    )
    for (family, form, kind, result), n in sorted(grouped.items()):
        summary[f"{family}/{form}/{kind}"][result] = n
    Path(args.out).write_text(
        json.dumps({"model": args.model, "seed": SEED, "summary": summary, "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
