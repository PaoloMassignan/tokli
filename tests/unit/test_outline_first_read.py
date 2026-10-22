"""SPEC 019 `outline_first_read` (S8j): PR-040…PR-046, AC-PR-27…AC-PR-33, "Shell file reads
(Claude Code)"; SPEC 009 CC-021 (c) (S8j SCR-001). All files are synthetic."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.helpers import FakeCounter, view_of
from tests.unit.test_engine import settings_for
from tokli.compression.engine import Engine, EngineSettings
from tokli.compressors.duplicate_tool_results import DuplicateToolResults
from tokli.compressors.outline_first_read import (
    SPEC,
    OutlineFirstRead,
    ShellRead,
    classify_shell_read,
)
from tokli.compressors.reread_by_reference import RereadByReference
from tokli.domain.models import SegmentKind, Span
from tokli.protocols.anthropic_messages import parse, render

KINDS = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})
PY = [
    '"""Synthetic module harbor."""',
    "",
    "from __future__ import annotations",
    "",
    "import logging",
    "",
    "LOG = logging.getLogger(__name__)",
    "",
    "",
    "def load_harbor(count: int, label: str) -> int:",
    '    """Load the synthetic harbor."""',
    "    limit = 4012",
    "    total = 0",
    "    for step in range(count):",
    "        total += step",
    "    return total % limit",
    "",
    "",
    "class Quartz:",
    '    """A synthetic class."""',
    "",
    "    def __init__(self, size: int) -> None:",
    "        self.size = size",
    "        self.window = 6367",
    "",
    "    @property",
    "    def area(self) -> int:",
    "        margin = 1390",
    "        return self.size * margin",
]
PY_TEXT = "\n".join(PY) + "\n"
SHELL_NOTE = "[tokli: lines {a}-{b} omitted — run the command again for them]"
READ_NOTE = "[tokli: lines {a}-{b} omitted — read the file again for them]"


def py_outline(note: str) -> str:
    rows = [
        *PY[:10],
        "    " + note.format(a=11, b=18),  # a maximal run: the two blank lines join it
        *PY[18:22],
        "        " + note.format(a=23, b=25),
        *PY[25:],
    ]
    return "\n".join(rows) + "\n"


CS = [
    "using System;",
    "",
    "namespace Synthetic.Harbor",
    "{",
    "    public sealed class Quartz",
    "    {",
    "        private readonly int _size;",
    "",
    "        public Quartz(int size)",
    "        {",
    "            _size = size;",
    "            var window = 6367;",
    "            Console.WriteLine(window);",
    "        }",
    "",
    "        public int Area()",
    "        {",
    "            var margin = 1390;",
    "            return _size * margin;",
    "        }",
    "    }",
    "}",
]
CS_TEXT = "\n".join(CS) + "\n"


def numbered(text: str) -> str:
    """Claude Code's `Read` numbering: `{n}\\t<line>`."""
    return "\n".join(f"{n}\t{line}" for n, line in enumerate(text.split("\n")[:-1], 1)) + "\n"


def call(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}],
    }


def result(call_id: str, text: str, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return {"role": "user", "content": [block]}


def body(*exchanges: tuple[str, dict[str, Any], str]) -> dict[str, Any]:
    """A conversation: one human turn, then one tool call and result per exchange, then a
    question. Each exchange is (tool, arguments, result text)."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Look at the synthetic repo."}]
    for n, (tool, args, text) in enumerate(exchanges):
        messages += [call(f"toolu_{n}", tool, args), result(f"toolu_{n}", text)]
    messages.append({"role": "user", "content": "What next?"})
    return {"model": "claude-test", "max_tokens": 64, "messages": messages}


def run(data: dict[str, Any], *extra: Any, spans: Any = None, settings: Any = None, **options: Any):  # type: ignore[no-untyped-def]
    request = parse(json.dumps(data).encode(), mutable_kinds=KINDS)
    pruner = OutlineFirstRead(**{"min_tokens": 0, **options})
    compressors = [pruner, *extra]
    enabled = [c.spec.id for c in compressors]
    engine = Engine(compressors, settings or settings_for(*enabled, min_segment_tokens=0))
    outcome = engine.run(request, view_of(request, spans=spans), FakeCounter(), None)
    return request, outcome, json.loads(render(request, outcome.patches))


def results_of(forwarded: dict[str, Any]) -> list[str]:
    return [
        block["content"]
        for message in forwarded["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]


def reasons(outcome: Any) -> dict[str, int]:
    stat = next(s for s in outcome.stats if s.compressor_id == "outline_first_read")
    return {k: v for k, v in stat.skip_reasons.items() if k.startswith("not_applicable")}


# -- declaration and defaults (PR-040, AC-PR-27) --------------------------------------------


def test_outline_off_by_default_and_declared() -> None:
    """PR-040: SELECTIVE, request scope, prefix-stable, off by default, with its assumption and
    its target tools."""
    from tokli.config.schema import TokliSettings

    assert (SPEC.kind, SPEC.scope, SPEC.prefix_stable, SPEC.default_enabled) == (
        "SELECTIVE",
        "request",
        True,
        False,
    )
    assert SPEC.assumptions == ("outline_suffices_until_reread",)
    assert OutlineFirstRead().spec.target_tools == frozenset({"Read", "Bash", "PowerShell"})
    settings = TokliSettings()
    assert settings.compressors.outline_first_read.enabled is False
    assert settings.pruning.outline_tools == ["Read", "Bash", "PowerShell"]
    assert settings.pruning.outline_min_tokens == 500
    assert settings.pruning.outline_min_run_lines == 3
    assert settings.pruning.outline_rules["py"] == "python"
    assert settings.pruning.outline_rules["cs"] == "c_family"
    assert "md" not in settings.pruning.outline_rules


def test_lossless_only_switches_outline_off() -> None:
    """AC-PR-27, CC-002: a SELECTIVE compressor, so the "Lossless only" shortcut (which switches
    off every non-LOSSLESS compressor) switches it off, and enabling it makes the policy
    LOSSY_ALLOWED."""
    on = Engine([OutlineFirstRead()], settings_for("outline_first_read"))
    off = Engine([OutlineFirstRead()], settings_for())
    assert (on.policy, off.policy) == ("LOSSY_ALLOWED", "LOSSLESS_ONLY")


# -- candidates (PR-041, AC-PR-27) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "args", "text", "reason"),
    [
        ("Read", {"file_path": "src/a.py"}, numbered(PY_TEXT), None),
        ("Bash", {"command": "cat src/a.py"}, PY_TEXT, None),
        ("Bash", {"command": "cd src && cat a.py"}, PY_TEXT, None),
        ("PowerShell", {"command": "Get-Content src/a.py"}, PY_TEXT, None),
        ("Read", {"file_path": "src/a.py", "offset": 10}, numbered(PY_TEXT), "partial_read"),
        ("Bash", {"command": "sed -n 1,40p src/a.py"}, PY_TEXT, "partial_read"),
        ("Bash", {"command": "head -n 40 src/a.py"}, PY_TEXT, "partial_read"),
        ("Bash", {"command": "cat src/a.py | head"}, PY_TEXT, "not_file_read"),
        ("Bash", {"command": "pytest -q"}, PY_TEXT, "not_file_read"),
        ("Grep", {"pattern": "def"}, PY_TEXT, "not_file_read"),
        ("Bash", {"command": "cat docs/spec.md"}, PY_TEXT, "no_outline_rule"),
        ("Bash", {"command": "cat notes.txt"}, PY_TEXT, "no_outline_rule"),
    ],
)
def test_outline_candidates_and_reasons(
    tool: str, args: dict[str, Any], text: str, reason: str | None
) -> None:
    """AC-PR-27: whole reads of a code file are candidates; every other result is left alone,
    with its reason."""
    _, outcome, forwarded = run(body((tool, args, text)))
    if reason is None:
        assert results_of(forwarded) != [text]
        assert reasons(outcome) == {}
    else:
        assert results_of(forwarded) == [text]
        assert reasons(outcome) == {f"not_applicable({reason})": 1}


def test_outline_skips_errors_and_small_results() -> None:
    """AC-PR-27: an `is_error` result and a result under `outline_min_tokens` stay whole."""
    data = body(("Bash", {"command": "cat src/a.py"}, PY_TEXT))
    data["messages"][2]["content"][0]["is_error"] = True
    _, outcome, forwarded = run(data)
    assert results_of(forwarded) == [PY_TEXT]
    assert reasons(outcome) == {"not_applicable(error_result)": 1}
    _, outcome, forwarded = run(
        body(("Bash", {"command": "cat src/a.py"}, PY_TEXT)), min_tokens=len(PY_TEXT) + 1
    )
    assert results_of(forwarded) == [PY_TEXT]
    assert reasons(outcome) == {"not_applicable(below_min_tokens)": 1}


# -- the outline (PR-043, PR-044, AC-PR-29) -------------------------------------------------


def test_outline_python_keeps_declarations_and_head() -> None:
    """AC-PR-29: the first 8 lines, declarations and unindented lines are kept verbatim; each
    run of at least 3 other lines becomes one note, indented like its first line."""
    _, _, forwarded = run(body(("Bash", {"command": "cat src/a.py"}, PY_TEXT)))
    assert results_of(forwarded) == [py_outline(SHELL_NOTE)]


def test_outline_c_family() -> None:
    """AC-PR-29: the `c_family` rule on a C# file."""
    expected = (
        "\n".join(
            [
                *CS[:9],
                "        " + SHELL_NOTE.format(a=10, b=15),
                CS[15],
                "        " + SHELL_NOTE.format(a=17, b=22),
            ]
        )
        + "\n"
    )
    _, _, forwarded = run(body(("Bash", {"command": "cat src/Quartz.cs"}, CS_TEXT)))
    assert results_of(forwarded) == [expected]


def test_outline_note_format_and_numbering() -> None:
    """AC-PR-29: a `Read` result keeps its `{n}\\t` numbering on the kept lines, and its notes
    give the file's line numbers and say "read the file again"."""
    _, _, forwarded = run(body(("Read", {"file_path": "src/a.py"}, numbered(PY_TEXT))))
    (outlined,) = results_of(forwarded)
    rows = outlined.split("\n")
    assert rows[9] == "10\tdef load_harbor(count: int, label: str) -> int:"
    assert rows[10] == "    " + READ_NOTE.format(a=11, b=18)
    assert "        " + READ_NOTE.format(a=23, b=25) in rows
    assert rows[-2] == "29\t        return self.size * margin"


def test_outline_crlf() -> None:
    """PR-044: lines are split on `\\n`; each `\\r` stays on its line, and a note takes one."""
    crlf = PY_TEXT.replace("\n", "\r\n")
    _, _, forwarded = run(body(("Bash", {"command": "cat src/a.py"}, crlf)))
    assert results_of(forwarded) == [py_outline(SHELL_NOTE).replace("\n", "\r\n")]


def test_outline_keeps_protected_spans() -> None:
    """PR-044: a line that holds part of a protected span (a `<system-reminder>`) is kept,
    even inside a run that is otherwise omitted."""
    reminder = "<system-reminder>synthetic reminder</system-reminder>"
    # A longer body, so that the outline saves tokens and passes the engine's gain gate.
    rows = [*PY[:15], *(f"        total += step * {k}" for k in range(20)), *PY[15:]]
    rows[12] = "    " + reminder
    text = "\n".join(rows) + "\n"
    last_omitted = rows.index("class Quartz:")  # 1-based number of the line before it
    data = body(("Bash", {"command": "cat src/a.py"}, text))
    request = parse(json.dumps(data).encode(), mutable_kinds=KINDS)
    sid = next(s.id for s in request.segments if s.kind is SegmentKind.TOOL_RESULT)
    start = text.index(reminder)
    _, _, forwarded = run(data, spans={sid: (Span(start, start + len(reminder), "reminder"),)})
    (outlined,) = results_of(forwarded)
    assert "    " + reminder in outlined.split("\n")
    assert "    " + SHELL_NOTE.format(a=14, b=last_omitted) in outlined.split("\n")


# -- first read only (PR-042, AC-PR-28) -----------------------------------------------------


def test_outline_only_first_read_of_a_file() -> None:
    """AC-PR-28: the first read is outlined; every later read of the same file, in any form, is
    forwarded whole; a file written or edited before it was read is never outlined; two
    spellings of one path are the same file."""
    _, outcome, forwarded = run(
        body(
            ("Bash", {"command": "cat src/a.py"}, PY_TEXT),
            ("Read", {"file_path": "C:/repo/src/a.py"}, numbered(PY_TEXT)),
            ("Bash", {"command": "cat src/a.py"}, PY_TEXT),
        )
    )
    first, second, third = results_of(forwarded)
    assert first == py_outline(SHELL_NOTE)
    assert (second, third) == (numbered(PY_TEXT), PY_TEXT)
    assert reasons(outcome) == {"not_applicable(seen_before)": 2}

    for earlier in (
        ("Write", {"file_path": "src/a.py", "content": PY_TEXT}, "File created."),
        ("Edit", {"file_path": "src/a.py", "old_string": "a", "new_string": "b"}, "Done."),
        ("Bash", {"command": "sed -n 1,5p src/a.py"}, "\n".join(PY[:5]) + "\n"),
    ):
        _, _, forwarded = run(body(earlier, ("Bash", {"command": "cat src/a.py"}, PY_TEXT)))
        assert results_of(forwarded)[-1] == PY_TEXT, earlier[0]


# -- prefix stability and structure (PR-045, PR-046, AC-PR-30) ------------------------------


def test_outline_prefix_stable_across_turns() -> None:
    """AC-PR-30: request N+1 adds a second read of the outlined file; its forwarded body starts
    with N's forwarded messages, byte for byte; one accepted segment; history never rewritten."""
    first = body(("Bash", {"command": "cat src/a.py"}, PY_TEXT))
    second = json.loads(json.dumps(first))
    second["messages"][-1:] = [
        {"role": "user", "content": "Show it again."},
        call("toolu_9", "Bash", {"command": "cat src/a.py"}),
        result("toolu_9", PY_TEXT),
        {"role": "user", "content": "What next?"},
    ]
    _, _, forwarded_n = run(first)
    _, outcome_m, forwarded_m = run(second)
    shared = len(first["messages"]) - 1
    assert forwarded_m["messages"][:shared] == forwarded_n["messages"][:shared]
    assert json.dumps(forwarded_m["messages"][:shared]) == json.dumps(
        forwarded_n["messages"][:shared]
    )
    assert results_of(forwarded_m)[-1] == PY_TEXT
    stat = next(s for s in outcome_m.stats if s.compressor_id == "outline_first_read")
    assert stat.accepted == 1
    assert SPEC.prefix_stable is True


def test_outline_preserves_structure() -> None:
    """PR-005: only the outlined string changes; messages, blocks, ids and arguments stay."""
    data = body(
        ("Bash", {"command": "cat src/a.py"}, PY_TEXT),
        ("Read", {"file_path": "src/Quartz.cs"}, numbered(CS_TEXT)),
    )
    _, _, forwarded = run(data)
    restored = json.loads(json.dumps(forwarded))
    restored["messages"][2]["content"][0]["content"] = PY_TEXT
    restored["messages"][4]["content"][0]["content"] = numbered(CS_TEXT)
    assert restored == data


# -- later references (CC-019, AC-PR-31) ----------------------------------------------------


def test_outline_later_references_forward_whole() -> None:
    """AC-PR-31: a later identical read (`duplicate_tool_results`) and a re-read after an edit
    (`reread_by_reference`) of an outlined file are forwarded whole; no stub names it."""
    read = ("Read", {"file_path": "src/a.py"}, numbered(PY_TEXT))
    _, _, forwarded = run(body(read, read), DuplicateToolResults(0))
    first, second = results_of(forwarded)
    assert first.count("[tokli: lines") == 2
    assert second == numbered(PY_TEXT)

    edited = PY_TEXT.replace("limit = 4012", "limit = 4013")
    edit = ("Edit", {"file_path": "src/a.py", "old_string": "4012", "new_string": "4013"}, "Done.")
    reread = ("Read", {"file_path": "src/a.py"}, numbered(edited))
    _, _, forwarded = run(body(read, edit, reread), RereadByReference(("Read",), 5, 20000))
    first, _done, third = results_of(forwarded)
    assert first.count("[tokli: lines") == 2
    assert third == numbered(edited)


# -- CC-021 (c) (AC-PR-32) ------------------------------------------------------------------


def test_outline_applies_to_declared_verbatim_tools() -> None:
    """AC-PR-32, CC-021 (c): `Read`, `Bash` and `PowerShell` are verbatim tools, yet the pruner
    acts on them through its declared target tools, with no `apply_to_verbatim_tools`."""
    settings = EngineSettings(
        enabled={"outline_first_read": True},
        verbatim_tools=frozenset({"Read", "Bash", "PowerShell", "shell"}),
        min_segment_tokens=0,
    )
    _, _, forwarded = run(
        body(
            ("Read", {"file_path": "src/a.py"}, numbered(PY_TEXT)),
            ("Bash", {"command": "cat src/b.py"}, PY_TEXT),
            ("PowerShell", {"command": "Get-Content src/Quartz.cs"}, CS_TEXT),
        ),
        settings=settings,
    )
    assert all("[tokli: lines" in text for text in results_of(forwarded))
    # A tool outside its target tools stays under the verbatim filter.
    _, outcome, forwarded = run(
        body(("Bash", {"command": "cat src/a.py"}, PY_TEXT)), settings=settings, tools=("Read",)
    )
    assert results_of(forwarded) == [PY_TEXT]
    stat = next(s for s in outcome.stats if s.compressor_id == "outline_first_read")
    assert stat.skip_reasons.get("verbatim_tool") == 1


def test_target_tools_require_selective_off_by_default() -> None:
    """S8j SCR-001: the registry accepts `target_tools` only on a SELECTIVE compressor that is
    off by default."""
    from dataclasses import replace

    from tokli.compression.registry import REGISTRY, validate_registry

    validate_registry(REGISTRY)

    class Bad(OutlineFirstRead):
        pass

    for change in ({"kind": "LOSSLESS"}, {"default_enabled": True}):
        bad = Bad()
        bad.spec = replace(bad.spec, **change)  # type: ignore[misc]
        with pytest.raises(ValueError, match="target_tools"):
            validate_registry((bad,))


# -- Claude Code shell reads (AC-PR-33) -----------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat src/a.py", ShellRead("src/a.py", whole=True)),
        ("cat -n src/a.py", ShellRead("src/a.py", whole=True)),
        ("nl src/a.py", ShellRead("src/a.py", whole=True)),
        ("type src\\a.py", ShellRead("src/a.py", whole=True)),
        ("Get-Content src/a.py", ShellRead("src/a.py", whole=True)),
        ("get-content -Path 'src/a b.py'", ShellRead("src/a b.py", whole=True)),
        ("cd repo && cat src/a.py", ShellRead("repo/src/a.py", whole=True)),
        ('cd "C:\\my repo" && cat a.py', ShellRead("c:/my repo/a.py", whole=True)),
        ("cd repo && cat /abs/a.py", ShellRead("/abs/a.py", whole=True)),
        ("sed -n 1,80p src/a.py", ShellRead("src/a.py", whole=False)),
        ("sed -n '40,90p' src/a.py", ShellRead("src/a.py", whole=False)),
        ("head -n 20 src/a.py", ShellRead("src/a.py", whole=False)),
        ("head -20 src/a.py", ShellRead("src/a.py", whole=False)),
        ("tail src/a.py", ShellRead("src/a.py", whole=False)),
        ("Get-Content src/a.py -TotalCount 20", ShellRead("src/a.py", whole=False)),
        ("Get-Content src/a.py -Head 20", ShellRead("src/a.py", whole=False)),
        ("Get-Content src/a.py -Tail 5", ShellRead("src/a.py", whole=False)),
        ("cat src/a.py | head", None),
        ("cat a.py; ls", None),
        ("cat a.py & ls", None),
        ("cat a.py > b.py", None),
        ("cat `ls`", None),
        ("cat $(ls)", None),
        ("cat a.py\nls", None),
        ("cat a.py b.py", None),
        ("cat -A a.py", None),
        ("sed -n 1,x0p a.py", None),
        ("sed 1,80p a.py", None),
        ("head -n twenty a.py", None),
        ("Get-Content -Raw a.py", None),
        ("cd repo && cd src && cat a.py", None),
        ("grep def a.py", None),
        ("cat", None),
        ("", None),
    ],
)
def test_claude_code_shell_read_rules(command: str, expected: ShellRead | None) -> None:
    """AC-PR-33: every rule row, the `cd <dir> &&` prefix, quotes, and each rejection."""
    assert classify_shell_read(command) == expected
