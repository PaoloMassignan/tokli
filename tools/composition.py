"""Composition of the cached context (S8k; TOKLI_TEST_STRATEGY §2): which parts of the human's
recent Claude Code contexts the cache cost belongs to, measured locally.

Nothing is sent anywhere, and nothing is written. Only counters are printed: per part of the
context, its tokens, its tokens re-read from the cache, and its tokens written again at full
rewrites. No text, path, command or argument is printed. Consent is asked on every run.

How a session is measured:
1. The session file is read in order; subagent side-chains are left out. A compaction boundary
   closes a context, and the compaction summary starts the next one.
2. Every assistant message id is one request, which reads every block before it in its context.
3. Of the L later requests of a block, the first writes it to the cache. Each of the other L - 1
   reads it, or writes it again when that request is a full rewrite (its exact cache write is at
   least half of its input). So re-read = tokens x (L - 1 - R) and rewrite = tokens x R.
4. The system prompt and the tool definitions are not in the session files. The fixed part of a
   context is the intercept of a least-squares line through its requests: provider input tokens
   (exact usage) against the estimated tokens of the blocks before each request. The slope is the
   ratio between provider and estimated tokens. The fixed part is reported in estimated tokens.
5. The cost share uses the one-hour cache price ratios: a write costs 2, a read 0.1.

Usage:
    python -m tools.composition [--days 7] [--yes]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tokli.app.bootstrap import bootstrap
from tokli.compressors.outline_first_read import SHELL_TOOLS, classify_shell_read
from tokli.compressors.reread_by_reference import normalise_path
from tokli.config import CliOverrides, load_config
from tools.replay import SESSIONS, session_files

WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
MARKDOWN_EXTS = frozenset({"md", "markdown", "mdx"})
FIXED = "fixed part"
WRITE_PRICE, READ_PRICE = 2.0, 0.1
_CD = re.compile(r"^\s*cd\s+\S+\s*&&\s*")
_HARMLESS = re.compile(r"\s*(2>\s*/dev/null|2>&1|2>\$null)\s*$")
_BUILTIN = re.compile(r"^[A-Z][A-Za-z]{1,30}$")


@dataclass
class Totals:
    sessions: int = 0
    contexts: int = 0
    requests: int = 0
    rewrites: int = 0
    fitted_contexts: int = 0
    fixed_provider: list[float] = field(default_factory=list)
    k: list[float] = field(default_factory=list)
    raw: Counter[str] = field(default_factory=Counter)
    written: Counter[str] = field(default_factory=Counter)
    reread: Counter[str] = field(default_factory=Counter)
    rewrite: Counter[str] = field(default_factory=Counter)
    exact_cache_read: int = 0  # provider usage, summed over the requests that report it
    exact_cache_write: int = 0


@dataclass
class _Request:
    usage: dict[str, Any] | None
    before: int = 0  # estimated tokens of the blocks before it

    @property
    def total(self) -> int | None:
        u = self.usage
        if not u:
            return None
        parts = (
            u.get("input_tokens"),
            u.get("cache_read_input_tokens"),
            u.get("cache_creation_input_tokens"),
        )
        if not all(isinstance(p, int) for p in parts):
            return None
        return sum(parts)  # type: ignore[arg-type]

    @property
    def is_rewrite(self) -> bool:
        total = self.total
        written = (self.usage or {}).get("cache_creation_input_tokens")
        return bool(total) and isinstance(written, int) and written * 2 >= total  # type: ignore[operator]


@dataclass
class _Context:
    # each step is a block (part, tokens) or a request
    steps: list[tuple[str, int] | _Request] = field(default_factory=list)


def _ext(path: str) -> str:
    name = normalise_path(path).rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _file_kind(paths: Sequence[str], code_exts: Collection[str]) -> str:
    exts = {_ext(p) for p in paths}
    if exts & set(code_exts):
        return "code"
    if exts & MARKDOWN_EXTS:
        return "Markdown"
    return "other files"


def _tool(name: Any) -> str:
    if isinstance(name, str) and name.startswith("mcp__"):
        return "MCP tools"
    return name if isinstance(name, str) and _BUILTIN.match(name) else "other tools"


def _read_paths(name: Any, args: dict[str, Any]) -> list[str]:
    """The files one call reads: `Read`, or shell reads joined by `&&`, `;` or newlines."""
    if name == "Read":
        path = args.get("file_path")
        return [path] if isinstance(path, str) else []
    command = args.get("command")
    if name not in SHELL_TOOLS or not isinstance(command, str):
        return []
    paths = []
    for segment in re.split(r"&&|;|\n", _CD.sub("", command.strip())):
        segment = _HARMLESS.sub("", segment.strip())
        read = classify_shell_read(segment) if segment else None
        if read is not None:
            paths.append(read.path)
    return paths


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _contexts(path: Path, counter: Any, code_exts: Collection[str]) -> Iterator[_Context]:
    context = _Context()
    requests: dict[str, _Request] = {}
    calls: dict[str, tuple[Any, dict[str, Any]]] = {}

    def block(part: str, text: str) -> None:
        if text:
            context.steps.append((part, counter.count(text)))

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("isSidechain"):
                continue
            if event.get("subtype") == "compact_boundary":
                if context.steps:
                    yield context
                context, requests = _Context(), {}
                continue
            message = event.get("message")
            if event.get("type") not in ("user", "assistant") or not isinstance(message, dict):
                continue
            content = message.get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            if not isinstance(blocks, list):
                continue
            if message.get("role") == "assistant":
                mid = message.get("id")
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
                if not isinstance(mid, str) or mid not in requests:
                    request = _Request(usage)
                    if isinstance(mid, str):
                        requests[mid] = request
                    context.steps.append(request)
                elif usage is not None:
                    requests[mid].usage = usage  # later events of one message repeat its usage
            elif message.get("role") != "user":
                continue
            summary = event.get("isCompactSummary")
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                if kind == "text":
                    role = "compaction summary" if summary else f"{message['role']} text"
                    block(role, b.get("text") or "")
                elif kind == "thinking":
                    block("thinking", b.get("thinking") or "")
                elif kind == "tool_use":
                    name, args = b.get("name"), b.get("input")
                    args = args if isinstance(args, dict) else {}
                    calls[str(b.get("id"))] = (name, args)
                    if name in WRITE_TOOLS:
                        target = args.get("file_path") or args.get("notebook_path")
                        kind_ = _file_kind([target] if isinstance(target, str) else [], code_exts)
                        part = f"write arguments: {kind_}"
                    else:
                        part = f"call arguments: {_tool(name)}"
                    block(part, json.dumps(args, ensure_ascii=False))
                elif kind == "tool_result":
                    name, args = calls.get(str(b.get("tool_use_id")), (None, {}))
                    reads = _read_paths(name, args)
                    if reads:
                        part = f"read results: {_file_kind(reads, code_exts)}"
                    elif name in WRITE_TOOLS:
                        part = "results: write tools"
                    else:
                        part = f"results: {_tool(name)}"
                    block(part, _text(b.get("content")))
    if context.steps:
        yield context


def _fit(requests: Sequence[_Request]) -> tuple[float, float] | None:
    """(intercept, slope) of provider tokens against estimated tokens, if the fit is sound."""
    points = [(r.before, r.total) for r in requests if r.total is not None]
    xs = [float(x) for x, _ in points]
    if len(points) < 2 or len(set(xs)) < 2:
        return None
    ys = [float(y) for _, y in points]
    slope, intercept = statistics.linear_regression(xs, ys)
    if slope <= 0 or intercept < 0:
        return None
    return intercept, slope


def _account(totals: Totals, context: _Context) -> None:
    requests = [s for s in context.steps if isinstance(s, _Request)]
    totals.contexts += 1
    totals.requests += len(requests)
    totals.rewrites += sum(r.is_rewrite for r in requests)
    for r in requests:
        if r.total is not None and r.usage is not None:
            totals.exact_cache_read += r.usage["cache_read_input_tokens"]
            totals.exact_cache_write += r.usage["cache_creation_input_tokens"]
    seen = 0
    for step in context.steps:
        if isinstance(step, _Request):
            step.before = seen
        else:
            seen += step[1]
    # walking backwards: the requests after a step, and the full rewrites after the first of them
    later, rewrites_after = 0, 0  # rewrites_after: among the requests after the next one
    pending_rewrite = False  # whether the next request is a rewrite (not yet counted)
    for step in reversed(context.steps):
        if isinstance(step, _Request):
            if later:
                rewrites_after += pending_rewrite
            pending_rewrite = step.is_rewrite
            later += 1
            continue
        part, tokens = step
        _add(totals, part, tokens, later, rewrites_after)
    fit = _fit(requests)
    if fit is not None:
        intercept, slope = fit
        totals.fitted_contexts += 1
        totals.fixed_provider.append(intercept)
        totals.k.append(slope)
        rewrites = sum(r.is_rewrite for r in requests[1:])
        _add(totals, FIXED, round(intercept / slope), len(requests), rewrites)


def _add(totals: Totals, part: str, tokens: int, later: int, rewrites: int) -> None:
    """One block with ``later`` requests after it, ``rewrites`` of them full rewrites after the
    first (which writes the block)."""
    totals.raw[part] += tokens
    if not later:
        return
    totals.written[part] += tokens
    totals.rewrite[part] += tokens * rewrites
    totals.reread[part] += tokens * (later - 1 - rewrites)


def measure(counter: Any, files: Sequence[Path], code_exts: Collection[str]) -> Totals:
    totals = Totals()
    for path in files:
        totals.sessions += 1
        for context in _contexts(path, counter, code_exts):
            _account(totals, context)
    return totals


def _cost(totals: Totals, part: str) -> float:
    return (
        WRITE_PRICE * (totals.written[part] + totals.rewrite[part])
        + READ_PRICE * totals.reread[part]
    )


def render(totals: Totals) -> str:
    lines = [
        f"sessions {totals.sessions}, contexts {totals.contexts}, requests {totals.requests}, "
        f"full rewrites {totals.rewrites}",
    ]
    if totals.fitted_contexts:
        lines.append(
            f"fixed part fitted in {totals.fitted_contexts} context(s): median "
            f"{statistics.median(totals.fixed_provider):,.0f} provider tokens, median provider/"
            f"estimate ratio {statistics.median(totals.k):.2f}"
        )
    else:
        lines.append("fixed part: unavailable (no context with usage to fit)")
    reread, written = sum(totals.reread.values()), sum(totals.written.values())
    rewritten = sum(totals.rewrite.values())
    if totals.k and totals.exact_cache_read:
        k = statistics.median(totals.k)
        lines.append(
            f"check: modelled re-reads x ratio = {reread * k:,.0f} provider tokens, exact cache "
            f"reads {totals.exact_cache_read:,}; modelled writes x ratio = "
            f"{(written + rewritten) * k:,.0f}, exact cache writes {totals.exact_cache_write:,}"
        )
    cost = WRITE_PRICE * (written + rewritten) + READ_PRICE * reread or 1.0
    lines.append(
        f"input-side cost: first writes {WRITE_PRICE * written / cost:.1%}, full rewrites "
        f"{WRITE_PRICE * rewritten / cost:.1%}, cache reads {READ_PRICE * reread / cost:.1%}"
    )
    parts = sorted(totals.raw, key=lambda p: _cost(totals, p), reverse=True)
    all_cost = sum(_cost(totals, p) for p in parts) or 1.0
    all_reread = sum(totals.reread.values()) or 1
    all_rewrite = sum(totals.rewrite.values()) or 1
    lines += [
        "",
        f"{'part':<30}{'tokens':>12}{'re-read':>15}{'share':>7}{'rewritten':>13}{'share':>7}"
        f"{'cost share':>12}",
    ]
    for part in parts:
        lines.append(
            f"{part:<30}{totals.raw[part]:>12,.0f}{totals.reread[part]:>15,.0f}"
            f"{totals.reread[part] / all_reread:>7.1%}{totals.rewrite[part]:>13,.0f}"
            f"{totals.rewrite[part] / all_rewrite:>7.1%}{_cost(totals, part) / all_cost:>12.1%}"
        )
    lines.append("")
    lines.append("cost share: input side only, one-hour cache prices (write 2, read 0.1)")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--days", type=int, default=7, help="sessions modified in the last N days (7)"
    )
    parser.add_argument("--sessions-dir", default=str(SESSIONS), help=argparse.SUPPRESS)
    parser.add_argument("--yes", action="store_true", help="consent given for this run")
    args = parser.parse_args(argv)
    files = session_files(Path(args.sessions_dir), args.days)
    print(
        f"This reads {len(files)} local Claude Code session file(s) from the last {args.days} "
        "day(s), measures them on this machine, sends nothing and writes nothing, and prints "
        "counters only."
    )
    if not args.yes and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("cancelled: nothing was read")
        return 1
    config = load_config(CliOverrides(), dict(os.environ), sys.platform)
    services = bootstrap(config, version="composition", telemetry=False)
    counter = services.selector.select("claude-composition")
    code_exts = frozenset(config.settings.pruning.outline_rules)
    print(render(measure(counter, files, code_exts)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
