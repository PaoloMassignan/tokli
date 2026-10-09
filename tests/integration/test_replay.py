"""S8h P4: the real-traffic replay reads Claude Code session files, replays them through the real
pipeline locally, and prints counters only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tools.replay import render, replay, session_files

from tests.integration.servers import BYTE_CATALOG, make_config
from tokli.app.bootstrap import bootstrap

CANARY = "TOKLI-REPLAY-CANARY"


def event(role: str, content: Any, **extra: Any) -> dict[str, Any]:
    return {"type": role, "message": {"role": role, "content": content, **extra}, "cwd": r"C:\work"}


def session(path: Path) -> None:
    """A Claude Code session file in its real shape: assistant blocks split over events that
    share a message id, `Read` numbered `"{n}\t"`, a compaction boundary, and a side-chain."""
    old = [f"line {n} {CANARY} = value_{n}" for n in range(1, 31)]
    new = [*old[:10], f"an inserted line {CANARY}", *old[10:]]

    def numbered(lines: list[str]) -> str:
        return "\n".join(f"{n}\t{line}" for n, line in enumerate(lines, start=1))

    def tool_use(cid: str, name: str, args: dict[str, Any], mid: str) -> dict[str, Any]:
        return event(
            "assistant", [{"type": "tool_use", "id": cid, "name": name, "input": args}], id=mid
        )

    def tool_result(cid: str, text: str) -> dict[str, Any]:
        return event("user", [{"type": "tool_result", "tool_use_id": cid, "content": text}])

    events = [
        event("user", f"Start the synthetic task {CANARY}."),
        event("assistant", [{"type": "text", "text": "Reading the file."}], id="msg_1"),
        tool_use("toolu_1", "Read", {"file_path": r"C:\work\mod.py"}, "msg_1"),
        tool_result("toolu_1", numbered(old)),
        tool_use(
            "toolu_2",
            "Edit",
            {
                "file_path": r"C:\work\mod.py",
                "old_string": "a",
                "new_string": "b",
                "replace_all": False,
            },
            "msg_2",
        ),
        tool_result("toolu_2", r"The file C:\work\mod.py has been updated successfully."),
        tool_use("toolu_3", "Read", {"file_path": r"C:\work\mod.py"}, "msg_3"),
        tool_result("toolu_3", numbered(new)),
        {"isSidechain": True, **event("user", f"side chain {CANARY}")},
        {"type": "system", "subtype": "compact_boundary"},
        event("user", f"After the compaction {CANARY}."),
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "project-a").mkdir(parents=True)
    session(root / "project-a" / "session-1.jsonl")
    return root


def services_for(tmp_path: Path, *sets: str):  # type: ignore[no-untyped-def]
    config = make_config(tmp_path, "http://127.0.0.1:9", *sets)
    return bootstrap(config, catalog=BYTE_CATALOG, version="test", telemetry=False)


def test_replay_counts_real_shapes(tmp_path: Path, sessions: Path) -> None:
    """The re-read after the edit, in Claude Code's numbering, is compressed in the replay."""
    services = services_for(tmp_path, "compressors.reread_by_reference.enabled=true")
    totals = replay(services, session_files(sessions, days=1))
    assert (totals.sessions, totals.requests) == (1, 2)  # two contexts around the compaction
    reread = totals.per_compressor["reread_by_reference"]
    assert reread["accepted"] == 1 and reread["saved"] > 0


def test_replay_prints_counters_only(tmp_path: Path, sessions: Path) -> None:
    totals = replay(services_for(tmp_path), session_files(sessions, days=1))
    text = render(totals)
    assert CANARY not in text and "mod.py" not in text and r"C:\work" not in text
    assert "considered" in text
