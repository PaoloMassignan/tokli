"""Real-traffic replay (S8h P4; TOKLI_TEST_STRATEGY §2): the human's recent Claude Code sessions
through the real pipeline, locally.

Nothing is sent anywhere, and nothing is written. Only counters are printed: how often each
compressor was considered, was applicable and was accepted, its main skip reasons, and the
estimated tokens it saved. No text, path, command or argument is printed. Consent is asked on
every run.

How a session is replayed:
1. The session file is read in order; subagent side-chains are left out.
2. A compaction boundary closes a context: the conversation up to it becomes one request (its
   last state), then the context starts again.
3. Consecutive events of one role are merged into one message, as the API receives them.
4. Each request goes through the pipeline with the effective configuration (plus any `--set`)
   and the provisioned tokenizers. Every tool result is seen once, in the last state of its
   context; prefix-stable compressors decide the same way as they did on the earlier requests.

Usage:
    python -m tools.replay [--days 7] [--set KEY=VALUE ...] [--yes]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tokli.app.bootstrap import Services, bootstrap
from tokli.compression.engine import EngineResult
from tokli.config import CliOverrides, load_config
from tokli.domain.stage import StageContext
from tokli.protocols.anthropic_messages import ParseError, parse

SESSIONS = Path.home() / ".claude" / "projects"


@dataclass
class Totals:
    sessions: int = 0
    requests: int = 0
    tool_result_tokens: int = 0
    per_compressor: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    skip_reasons: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))


def _contexts(path: Path) -> Iterator[list[dict[str, Any]]]:
    """The messages of each context of one session file (split at compaction boundaries)."""
    messages: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("isSidechain") or event.get("isCompactSummary"):
                continue
            if event.get("subtype") == "compact_boundary":
                if messages:
                    yield messages
                messages = []
                continue
            message = event.get("message")
            if event.get("type") not in ("user", "assistant") or not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in ("user", "assistant") or content in (None, "", []):
                continue
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            if not isinstance(blocks, list):
                continue
            if messages and messages[-1]["role"] == role:  # one message per turn, as sent
                messages[-1]["content"].extend(blocks)
                continue
            messages.append({"role": role, "content": list(blocks)})
    if messages:
        yield messages


def _engine_report(services: Services, body: Mapping[str, Any]) -> EngineResult | None:
    try:
        request = parse(
            json.dumps(body).encode("utf-8"),
            mutable_kinds=services.mutable_kinds,
            arg_fields=services.arg_fields or None,
        )
    except ParseError:
        return None
    result = services.pipeline.run(request, StageContext(request_id="replay"))
    report = result.reports.get("transform.compression")
    return report if isinstance(report, EngineResult) else None


def replay(services: Services, files: Sequence[Path]) -> Totals:
    totals = Totals()
    counter = services.selector.select("claude-replay")
    for path in files:
        totals.sessions += 1
        for messages in _contexts(path):
            body = {"model": "claude-replay", "max_tokens": 1024, "messages": messages}
            report = _engine_report(services, body)
            if report is None:
                continue
            totals.requests += 1
            for message in messages:
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        content = block.get("content")
                        text = content if isinstance(content, str) else json.dumps(content)
                        totals.tool_result_tokens += counter.count(text)
            for stat in report.stats:
                if not stat.considered:
                    continue
                c = totals.per_compressor[stat.compressor_id]
                c["considered"] += stat.considered
                c["applicable"] += stat.applicable
                c["accepted"] += stat.accepted
                c["saved"] += stat.marginal_saved
                totals.skip_reasons[stat.compressor_id].update(stat.skip_reasons)
    return totals


def render(totals: Totals) -> str:
    lines = [
        f"sessions {totals.sessions}, contexts replayed {totals.requests}, "
        f"tool-result tokens {totals.tool_result_tokens:,} (estimate)",
        "",
        f"{'compressor':<24}{'considered':>11}{'applicable':>11}{'accepted':>9}"
        f"{'saved':>10}{'share':>8}  main skip reasons",
    ]
    for cid in sorted(totals.per_compressor):
        c = totals.per_compressor[cid]
        share = c["saved"] / totals.tool_result_tokens if totals.tool_result_tokens else 0.0
        reasons = ", ".join(
            f"{reason} {n}" for reason, n in totals.skip_reasons[cid].most_common(3)
        )
        lines.append(
            f"{cid:<24}{c['considered']:>11}{c['applicable']:>11}{c['accepted']:>9}"
            f"{c['saved']:>10,}{share:>8.2%}  {reasons}"
        )
    return "\n".join(lines) + "\n"


def session_files(root: Path, days: int) -> list[Path]:
    cutoff = time.time() - days * 86400
    return sorted(p for p in root.glob("*/*.jsonl") if p.stat().st_mtime >= cutoff)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--days", type=int, default=7, help="sessions modified in the last N days (7)"
    )
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--sessions-dir", default=str(SESSIONS), help=argparse.SUPPRESS)
    parser.add_argument("--yes", action="store_true", help="consent given for this run")
    args = parser.parse_args(argv)
    files = session_files(Path(args.sessions_dir), args.days)
    print(
        f"This reads {len(files)} local Claude Code session file(s) from the last {args.days} "
        "day(s), replays them through Tokli on this machine, sends nothing and writes nothing, "
        "and prints counters only."
    )
    if not args.yes and input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
        print("cancelled: nothing was read")
        return 1
    config = load_config(CliOverrides(sets=tuple(args.sets)), dict(os.environ), sys.platform)
    services = bootstrap(config, version="replay", telemetry=False)
    print(render(replay(services, files)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
