"""E2 (S6, P6): the cache-economics experiment checks its own method before any paid run.

The dry run sends the scripted conversation through two real Tokli instances (compressors off
and default) to an in-process upstream that simulates the provider's prompt cache. Tokli's
positional prediction of the saving must match the saving observed from the two arms' usage.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from tests.integration.servers import BYTE_CATALOG, provision

SCRIPT = Path(__file__).resolve().parents[2] / "evals" / "experiments" / "e2_cache_economics.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("e2_cache_economics", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2_dry_run_self_test(tmp_path: Path) -> None:
    e2 = load()
    result = e2.dry_run(tmp_path, turns=8, catalog=BYTE_CATALOG, provision=provision)
    assert result["observed_saving_usd"] > 0
    assert result["predicted"]["method"] == "positional"
    assert abs(result["relative_error"]) <= 0.25, result
    assert result["verdict"] == "pass"


def test_e2_simulated_cache_reads_the_shared_prefix() -> None:
    """The simulator charges a cache read for the longest prefix cached by an earlier request
    (the provider looks back from each breakpoint), a cache write from there up to the request's
    last breakpoint, and uncached input after it."""
    e2 = load()
    cache = e2.SimulatedCache()
    first = [("a", 100, True), ("b", 50, True), ("c", 10, False)]
    assert cache.usage(first) == {"read": 0, "write": 150, "input": 10}
    second = [("a", 100, True), ("b", 50, False), ("d", 70, True), ("e", 5, False)]
    assert cache.usage(second) == {"read": 150, "write": 70, "input": 5}
