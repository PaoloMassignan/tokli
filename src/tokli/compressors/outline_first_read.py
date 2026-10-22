"""``outline_first_read``: the first whole read of a code file in a conversation is forwarded as
its skeleton; every later read of the same file is forwarded whole (SPEC 019 PR-040…PR-046,
S8j). SELECTIVE, prefix-stable, off by default.

The decision for a result reads only that result and the tool records before it, and the outline
is a pure function of the result's text and the configuration (PR-045), so a request forwards the
same prefix as the one before it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from tokli.compression.contract import CompressorSpec, Proposal, SegmentRef, ToolRecordView
from tokli.compressors.reread_by_reference import normalise_path
from tokli.domain.models import SegmentKind, Span
from tokli.domain.stage import ConversationView

DEFAULT_TOOLS = ("Read", "Bash", "PowerShell")
DEFAULT_RULES: Mapping[str, str] = {
    "py": "python",
    **{
        ext: "c_family"
        for ext in (
            "cs",
            "java",
            "kt",
            "ts",
            "tsx",
            "js",
            "jsx",
            "go",
            "rs",
            "c",
            "h",
            "cpp",
            "hpp",
        )
    },
}
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
FILE_TOOLS = ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit")
HEAD_LINES = 8

SPEC = CompressorSpec(
    id="outline_first_read",
    name="Skeleton at the first read",
    version="1",
    kind="SELECTIVE",
    equivalence="none",
    scope="request",
    prefix_stable=True,
    guarantees=(
        "only the first whole read of a code file changes (test_outline_only_first_read_of_a_file)",
        "kept lines, protected spans and numbering are verbatim "
        "(test_outline_keeps_protected_spans)",
        "prefix-stable (test_outline_prefix_stable_across_turns)",
    ),
    assumptions=("outline_suffices_until_reread",),
    stage="structural",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT}),
    min_tokens=0,
    cost_class="cheap",
    terminal=False,
    requires=(),
    default_enabled=False,  # E10(f): damage detected; exists by the human's decision (S8j)
    target_tools=frozenset(DEFAULT_TOOLS),
)

_RULES = {
    "python": re.compile(r"^\s*(@|def |class |async def )"),
    "c_family": re.compile(
        r"^\s*(public|private|protected|internal|static|export|async|override|virtual|abstract|"
        r"sealed|partial|func|fn|pub|impl|interface|class|struct|enum|record|namespace|type|"
        r"function)\b"
    ),
}
_NUMBERED = re.compile(r"^ *(\d+)\t")
NOTE = "[tokli: lines {a}-{b} omitted — {action} for them]"


# -- Claude Code shell reads ("Shell file reads (Claude Code)") -----------------------------


@dataclass(frozen=True)
class ShellRead:
    """A Claude Code shell command that reads one file: its normalised path, and whether the
    read is whole."""

    path: str
    whole: bool


_CD = re.compile(r"""^\s*cd\s+(?:"([^"]*)"|'([^']*)'|([^\s"'&]+))\s*&&\s*(.*)$""", re.DOTALL)
_INT = re.compile(r"^\d+$")


def _words(script: str) -> list[str] | None:
    """Whitespace-separated words, quotes honoured; ``None`` when the script is not a simple
    command (step 2 of the shell rules) or a quote is unbalanced."""
    words: list[str] = []
    current: list[str] = []
    quote: str | None = None
    started = False
    for i, ch in enumerate(script):
        if quote is not None:
            if ch == quote:
                quote = None
            else:
                current.append(ch)
        elif ch in "'\"":
            quote, started = ch, True
        elif ch in "|;&><`\n" or script.startswith("$(", i):
            return None
        elif ch.isspace():
            if current or started:
                words.append("".join(current))
                current, started = [], False
        else:
            current.append(ch)
    if quote is not None:
        return None
    if current or started:
        words.append("".join(current))
    return words


def _read_of(words: list[str]) -> tuple[str, bool] | None:
    """``(path, whole)`` for a read command, or ``None``."""
    if not words:
        return None
    program, args = words[0].lower().removesuffix(".exe"), words[1:]
    if program in ("cat", "type", "nl") and len(args) == 1 and not args[0].startswith("-"):
        return args[0], True
    if program == "cat" and len(args) == 2 and args[0] == "-n" and not args[1].startswith("-"):
        return args[1], True
    if program == "sed" and len(args) == 3 and args[0] == "-n":
        if re.fullmatch(r"\d+,\d+p", args[1]) and not args[2].startswith("-"):
            return args[2], False
        return None
    if program in ("head", "tail"):
        if len(args) == 1 and not args[0].startswith("-"):
            return args[0], False
        if len(args) == 2 and re.fullmatch(r"-\d+", args[0]) and not args[1].startswith("-"):
            return args[1], False
        if len(args) == 3 and args[0] == "-n" and _INT.match(args[1]):
            return (args[2], False) if not args[2].startswith("-") else None
        return None
    if program == "get-content":
        path: str | None = None
        whole = True
        i = 0
        while i < len(args):
            arg = args[i].lower()
            if arg == "-path" and i + 1 < len(args) and path is None:
                path, i = args[i + 1], i + 2
            elif arg in ("-totalcount", "-head", "-tail") and i + 1 < len(args):
                if not _INT.match(args[i + 1]):
                    return None
                whole, i = False, i + 2
            elif arg.startswith("-") or path is not None:
                return None
            else:
                path, i = args[i], i + 1
        return (path, whole) if path else None
    return None


def _is_absolute(path: str) -> bool:
    return path.startswith(("/", "\\", "~")) or bool(re.match(r"^[A-Za-z]:", path))


def classify_shell_read(command: str) -> ShellRead | None:
    """The file a Claude Code `Bash`/`PowerShell` command reads, per the shell rules."""
    directory = None
    match = _CD.match(command)
    if match is not None:
        directory = next(g for g in match.groups()[:3] if g is not None)
        command = match.group(4)
    words = _words(command)
    found = _read_of(words) if words is not None else None
    if found is None:
        return None
    path, whole = found
    if directory and not _is_absolute(path):
        path = directory.rstrip("/\\") + "/" + path
    return ShellRead(normalise_path(path), whole)


# -- the outline (PR-043, PR-044) -----------------------------------------------------------


def _protected_rows(rows: Sequence[str], spans: Iterable[Span]) -> set[int]:
    starts, offset = [], 0
    for row in rows:
        starts.append(offset)
        offset += len(row) + 1
    found: set[int] = set()
    for span in spans:
        for i, start in enumerate(starts):
            if start < span.end and span.start < start + len(rows[i]) + 1:
                found.add(i)
    return found


def outline(
    text: str, rule: str, action: str, min_run_lines: int, spans: Iterable[Span] = ()
) -> str | None:
    """The skeleton of ``text`` under ``rule``, or ``None`` when no run of omitted lines
    qualifies."""
    trailing = text.endswith("\n")
    rows = (text[:-1] if trailing else text).split("\n")
    protected = _protected_rows(rows, spans)
    keeps = _RULES[rule]
    keep: list[bool] = []
    numbers: list[int | None] = []
    contents: list[str] = []
    for i, row in enumerate(rows):
        line = row[:-1] if row.endswith("\r") else row
        match = _NUMBERED.match(line)
        content = line[match.end() :] if match else line
        numbers.append(int(match.group(1)) if match else None)
        contents.append(content)
        unindented = content.strip() != "" and content[:1] not in (" ", "\t")
        if rule == "c_family":
            unindented = unindented and content[:1] not in ("}", ")")
        keep.append(i < HEAD_LINES or i in protected or bool(keeps.match(content)) or unindented)
    out: list[str] = []
    omitted = False
    i = 0
    while i < len(rows):
        if keep[i]:
            out.append(rows[i])
            i += 1
            continue
        j = i
        while j < len(rows) and not keep[j]:
            j += 1
        if j - i >= min_run_lines:
            first, last = numbers[i], numbers[j - 1]
            a = first if first is not None else i + 1
            b = last if last is not None else j
            indent = contents[i][: len(contents[i]) - len(contents[i].lstrip(" \t"))]
            cr = "\r" if rows[i].endswith("\r") else ""
            out.append(indent + NOTE.format(a=a, b=b, action=action) + cr)
            omitted = True
        else:
            out.extend(rows[i:j])
        i = j
    if not omitted:
        return None
    return "\n".join(out) + ("\n" if trailing else "")


# -- the pruner (PR-040…PR-046) -------------------------------------------------------------


def _same_file(a: str, b: str) -> bool:
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def _touched(tool: ToolRecordView) -> str | None:
    """The file a tool record reads, writes or edits, normalised (PR-042)."""
    args = tool.arguments if isinstance(tool.arguments, dict) else {}
    if tool.name in FILE_TOOLS:
        path = args.get("file_path") or args.get("notebook_path")
        return normalise_path(path) if isinstance(path, str) else None
    if tool.name in SHELL_TOOLS and isinstance(args.get("command"), str):
        read = classify_shell_read(args["command"])
        return read.path if read is not None else None
    return None


class OutlineFirstRead:
    def __init__(
        self,
        tools: Sequence[str] = DEFAULT_TOOLS,
        rules: Mapping[str, str] = DEFAULT_RULES,
        min_tokens: int = 500,
        min_run_lines: int = 3,
    ) -> None:
        self.spec = replace(SPEC, target_tools=frozenset(tools))
        self._tools = frozenset(tools)
        self._rules = dict(rules)
        self._min_tokens = min_tokens
        self._min_run_lines = min_run_lines

    def _read(self, tool: ToolRecordView) -> tuple[str | None, str]:
        """``(path, "")`` for a whole read of one file, else ``(None, reason)``."""
        args = tool.arguments if isinstance(tool.arguments, dict) else {}
        if tool.name == "Read":
            path = args.get("file_path")
            if not isinstance(path, str):
                return None, "not_file_read"
            if args.get("offset") is not None or args.get("limit") is not None:
                return None, "partial_read"
            return normalise_path(path), ""
        if tool.name in SHELL_TOOLS and isinstance(args.get("command"), str):
            read = classify_shell_read(args["command"])
            if read is None:
                return None, "not_file_read"
            return (read.path, "") if read.whole else (None, "partial_read")
        return None, "not_file_read"

    def _decide(
        self,
        ref: SegmentRef,
        text: str,
        tool: ToolRecordView | None,
        earlier: Sequence[ToolRecordView],
        count: Callable[[str], int],
    ) -> tuple[str | None, str]:
        if tool is None or tool.name not in self._tools or not ref.whole_result:
            return None, "not_file_read"
        if ref.view.is_error:
            return None, "error_result"
        path, reason = self._read(tool)
        if path is None:
            return None, reason
        name = path.rsplit("/", 1)[-1]
        rule = self._rules.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
        if rule is None:
            return None, "no_outline_rule"
        if count(text) < self._min_tokens:
            return None, "below_min_tokens"
        if any(
            (seen := _touched(record)) is not None and _same_file(seen, path) for record in earlier
        ):
            return None, "seen_before"
        action = "read the file again" if tool.name == "Read" else "run the command again"
        skeleton = outline(text, rule, action, self._min_run_lines, ref.view.protected)
        return (skeleton, "") if skeleton is not None else (None, "no_omission")

    def plan(
        self,
        refs: Sequence[SegmentRef],
        texts: Mapping[str, str],
        tools: Sequence[ToolRecordView],
        count: Callable[[str], int],
        conversation: ConversationView | None = None,  # unused: prefix-stable by itself
    ) -> list[Proposal]:
        index = {t.call_id: i for i, t in enumerate(tools)}
        proposals: list[Proposal] = []
        for ref in refs:
            position = index.get(ref.call_id) if ref.call_id is not None else None
            tool = tools[position] if position is not None else None
            earlier = tools[:position] if position is not None else ()
            skeleton, reason = self._decide(ref, texts[ref.segment_id], tool, earlier, count)
            proposals.append(Proposal(ref.segment_id, skeleton, reason=reason))
        return proposals

    def decode_request(
        self, texts: Mapping[str, str], refs: Sequence[SegmentRef]
    ) -> dict[str, str]:
        return dict(texts)  # SELECTIVE: the omitted lines are not recoverable
