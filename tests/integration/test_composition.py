"""S8k: the composition of the cached context, measured on session files, counters only.

The tokenizer counts one token per UTF-8 byte (BYTE_CATALOG), so every expected count below is a
byte length.

Accounting of one block with L later requests in its context: the first of them writes it to the
cache; each of the other L - 1 either reads it, or writes it again when that request is a full
rewrite (R of them). So re-read = tokens x (L - 1 - R), rewrite = tokens x R.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tools import composition
from tools.composition import measure, render

from tests.integration.servers import BYTE_CATALOG, make_config
from tokli.app.bootstrap import bootstrap

CANARY = "TOKLI-COMPOSITION-CANARY"
CODE_EXTS = frozenset({"py", "cs"})


def counter_for(tmp_path: Path):  # type: ignore[no-untyped-def]
    config = make_config(tmp_path, "http://127.0.0.1:9")
    services = bootstrap(config, catalog=BYTE_CATALOG, version="test", telemetry=False)
    return services.selector.select("claude-composition")


def user(content: Any) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": content}}


def assistant(mid: str, blocks: list[dict[str, Any]], usage: dict[str, int] | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "id": mid, "content": blocks}
    if usage is not None:
        message["usage"] = usage
    return {"type": "assistant", "message": message}


def call(mid: str, cid: str, name: str, args: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return assistant(mid, [{"type": "tool_use", "id": cid, "name": name, "input": args}], **kw)


def result(cid: str, text: str) -> dict[str, Any]:
    return user([{"type": "tool_result", "tool_use_id": cid, "content": text}])


def usage(total: int, written: int = 0) -> dict[str, int]:
    return {
        "input_tokens": 0,
        "cache_read_input_tokens": total - written,
        "cache_creation_input_tokens": written,
    }


def write(root: Path, events: list[dict[str, Any]], name: str = "s.jsonl") -> list[Path]:
    (root / "project").mkdir(parents=True, exist_ok=True)
    path = root / "project" / name
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return [path]


def size(text: str) -> int:
    return len(text.encode("utf-8"))


START = f"Start the synthetic task {CANARY}."
WRITTEN = f"print('{CANARY}')\n" * 20
DOC = f"# Notes {CANARY}\n" * 10
CODE = f"def f():\n    return '{CANARY}'\n" * 10
TESTS = f"collected 3 items {CANARY}\n3 passed\n"


def task() -> list[dict[str, Any]]:
    """Five requests: msg_1 … msg_5."""
    return [
        user(START),
        call("msg_1", "t1", "Write", {"file_path": r"C:\work\mod.py", "content": WRITTEN}),
        result("t1", "File created successfully."),
        call("msg_2", "t2", "Read", {"file_path": "/work/NOTES.md"}),
        result("t2", DOC),
        call("msg_3", "t3", "Bash", {"command": "cat src/lib.py"}),
        result("t3", CODE),
        call("msg_4", "t4", "Bash", {"command": "pytest -q"}),
        result("t4", TESTS),
        assistant("msg_5", [{"type": "text", "text": "Done."}]),
    ]


def test_composition_counts_parts(tmp_path: Path) -> None:
    """Each part's tokens; with no usage there are no rewrites, so re-read = tokens x (L - 1)."""
    totals = measure(counter_for(tmp_path), write(tmp_path / "p", task()), CODE_EXTS)
    assert (totals.sessions, totals.contexts, totals.requests) == (1, 1, 5)
    expected = {
        "user text": (size(START), 4),
        "read results: Markdown": (size(DOC), 2),
        "read results: code": (size(CODE), 1),
        "results: Bash": (size(TESTS), 0),
        "results: write tools": (size("File created successfully."), 3),
    }
    for part, (tokens, reads) in expected.items():
        assert totals.raw[part] == tokens, part
        assert totals.written[part] == tokens, part
        assert totals.reread[part] == tokens * reads, part
    # the last block is never sent again, so it is never written to the cache
    assert totals.raw["assistant text"] == size("Done.")
    assert totals.written["assistant text"] == 0
    assert totals.reread["write arguments: code"] == 3 * totals.raw["write arguments: code"]
    assert totals.reread["call arguments: Read"] == 2 * totals.raw["call arguments: Read"]
    assert totals.raw["call arguments: Bash"] > 0
    assert totals.raw["write arguments: code"] > size(WRITTEN)  # the content and the path


def test_composition_weights_stop_at_compaction(tmp_path: Path) -> None:
    """A block is not re-read after the next compaction boundary; side-chains are left out."""
    events = [
        user(START),
        assistant("msg_1", [{"type": "text", "text": "One."}]),
        {"isSidechain": True, **user(f"side chain {CANARY}")},
        {"type": "system", "subtype": "compact_boundary"},
        {"isCompactSummary": True, **user(f"Summary {CANARY}.")},
        assistant("msg_2", [{"type": "text", "text": "Two."}]),
        assistant("msg_3", [{"type": "text", "text": "Three."}]),
    ]
    totals = measure(counter_for(tmp_path), write(tmp_path / "p", events), CODE_EXTS)
    assert (totals.contexts, totals.requests) == (2, 3)
    assert totals.written["user text"] == size(START)  # by msg_1, the only request of its context
    assert totals.reread["user text"] == 0  # msg_2 and msg_3 come after the compaction
    assert totals.reread["compaction summary"] == size(f"Summary {CANARY}.") * 1
    assert totals.raw["user text"] == size(START)  # the side chain is not counted


def test_composition_fixed_part_from_usage(tmp_path: Path) -> None:
    """The fixed part is the intercept of provider tokens against estimated content tokens.

    Provider total = 1000 + 2 x content, so the fit gives F = 1000 provider tokens, k = 2, and a
    fixed part of 500 estimated tokens, re-read by every request after the first."""
    a, b, c = "a" * 100, "b" * 300, "c" * 50
    events = [
        user(a),
        assistant("msg_1", [{"type": "text", "text": b}], usage=usage(1000 + 2 * 100)),
        user(c),
        assistant("msg_2", [{"type": "text", "text": "x"}], usage=usage(1000 + 2 * 450)),
        user("d" * 10),
        assistant("msg_3", [{"type": "text", "text": "y"}], usage=usage(1000 + 2 * 461)),
    ]
    totals = measure(counter_for(tmp_path), write(tmp_path / "p", events), CODE_EXTS)
    assert totals.fitted_contexts == 1
    assert totals.fixed_provider == [pytest.approx(1000)]
    assert totals.k == [pytest.approx(2)]
    assert totals.raw["fixed part"] == pytest.approx(500, abs=1)
    assert totals.reread["fixed part"] == pytest.approx(500 * 2, abs=2)


def test_composition_rewrites(tmp_path: Path) -> None:
    """A request whose cache write is at least half of its input is a full rewrite. For a block,
    it counts only after the request that first wrote that block."""
    events = [
        user(START),
        assistant("msg_1", [{"type": "text", "text": "One."}], usage=usage(5000, written=5000)),
        user("later"),
        assistant("msg_2", [{"type": "text", "text": "Two."}], usage=usage(5100, written=100)),
        assistant("msg_3", [{"type": "text", "text": "Three."}], usage=usage(5200, written=5200)),
    ]
    totals = measure(counter_for(tmp_path), write(tmp_path / "p", events), CODE_EXTS)
    assert totals.rewrites == 2  # msg_1 and msg_3
    assert totals.rewrite["user text"] == size(START) + size("later")  # both by msg_3
    assert totals.reread["user text"] == size(START)  # by msg_2
    assert totals.rewrite["assistant text"] == size("One.")  # "Two." is first written by msg_3
    assert (totals.exact_cache_read, totals.exact_cache_write) == (0 + 5000 + 0, 5000 + 100 + 5200)


def test_composition_prints_counters_only(tmp_path: Path) -> None:
    totals = measure(counter_for(tmp_path), write(tmp_path / "p", task()), CODE_EXTS)
    text = render(totals)
    for secret in (CANARY, "mod.py", "NOTES", "lib.py", "pytest", r"C:\work", "/work"):
        assert secret not in text, secret
    assert "re-read" in text and "write arguments: code" in text


def test_composition_asks_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --yes and with a "no", nothing is read."""
    write(tmp_path / "p", task())

    def must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("measured without consent")

    monkeypatch.setattr(composition, "measure", must_not_run)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert composition.main(["--sessions-dir", str(tmp_path / "p")]) == 1
    assert "nothing was read" in capsys.readouterr().out
