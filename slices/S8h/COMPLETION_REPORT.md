# S8h — Completion report

## Requirements implemented

| Item | What |
|---|---|
| SCR-001 | PR-032 and AC-PR-22: both numbering styles, `ambiguous_numbering`. `reread_by_reference` version 2. It was off by default until its version 2 smoke record (S8h Gate 1 decision, CC-020), and is **back on** with that record. |
| SCR-002 | `PowerShell` joins the default `verbatim_tools` (SPEC 017, SPEC 010). Approved: "metti powershell". |
| P2 | Format fixtures of real Claude Code shapes (`tests/fixtures/agent_formats/`), and a contract test that requires an expectation per registered compressor (`tests/contract/test_agent_formats.py`). |
| P3 | TC-021 (`not_applying` flag), UI-014 (Compressors page), OB-011 (informational `applicability` check in `/tokli/health`). |
| P4 | `tools/replay.py`, and the replay step in `CLAUDE.md` §2 and §7 and in `TOKLI_TEST_STRATEGY.md` §2. |
| P1 | The reread smoke families regenerated in Claude Code's numbering (case set `2026-10-09.1`). |

**Done before Gate 2:** the human's smoke run and the real-traffic replay (below).

## Tests and evidence

**RED, before the fix:**
- the regression test `test_reread_applies_to_claude_code_numbering` failed: the re-read was not
  replaced;
- the `Write`-source tests in both styles failed;
- the `not_applying` metrics test and the health `applicability` test failed on the missing
  field.

**Fixture corrected while writing it.** The first version of the format fixture interleaved the
`Grep` matches of different files. ripgrep groups them by file, so the fixture now does too.
This was a fixture shape error, not a compressor defect.

**Tests changed to the new defaults or fields, none weakened:**
- `test_reread_on_by_default_and_declared`: version 2, off until its record;
- `test_reread_by_reference_off_until_its_v2_record` (integration, was `_on_by_default`);
- `test_compressor_stats_only_for_considered`;
- `test_health_endpoint`: the new informational check;
- the default `config_hash` table and the doctor goldens.

**GREEN, local (Windows, CPython 3.11):** full suite with browser tests, 807 passed, 10 skipped,
plus the health fix after it; ruff, `mypy --strict` (src and tools) and `lint-imports` clean.

**CI:** run 37922412445 (commit 33b1322): all 12 jobs green; cross-job identity check green.
Final run 37927818275 (commit f63e62b): all 12 jobs and the identity check green.

## Real-traffic replay

Run on 2026-10-09 with the human's consent ("lancia il replay"): `python -m tools.replay --days
7 --set compressors.reread_by_reference.enabled=true`. 21 sessions, 33 contexts, about 8.8 M
tool-result tokens (estimate). The human's effective configuration was used, with
`search_group`, `log_filter` and `edit_args_on_resume` switched on from the dashboard.

| Compressor | Considered | Applicable | Accepted | Saved (share of tool-result tokens) |
|---|---|---|---|---|
| `reread_by_reference` v2 | 5,531 | 8 | 8 | 4,163 (0.05 %) |
| `duplicate_tool_results` | 4,259 | 18 | 18 | 1,590 (0.02 %) |
| `search_group` | 6,100 | 6 | 6 | 703 (0.01 %) |
| `json_minify` | 6,100 | 0 | 0 | 0 |
| `log_filter` | 6,100 | 0 | 0 | 0 |
| `edit_args_on_resume` | 1,272 | 781 | 781 | 1,412,700 (16 %, **not representative**) |

**Reading:**
- **The fix works on real traffic:** `reread_by_reference` was applicable 8 times, against 0
  before. But re-reads after an edit are rare in this traffic, so its value is small.
- **`edit_args_on_resume` is a replay artefact.** The replay has no conversation state, so every
  context counts as a resume (PR-021). Live, it applied 0 times that week. Its evaluation record
  is `damage_detected`; the human has it switched on, and it is recommended off.
- **Together, the lossless compressors save about 0.1 % of tool-result tokens** on this traffic,
  consistent with the dashboard. `Read` and `Bash` are excluded for every non-reference
  compressor, and most other results are too short.

## Smoke evaluation (version 2)

Run by the human on 2026-10-09 (`eval_s8h.cmd`): `claude-opus-5-5`, 3 repetitions, 396 calls.
The case sets are `2026-10-03.1` and `2026-10-09.1`; the latter is Claude Code's numbering.

| Family | Assumption | n | b | c | Errors (base / cand.) | Verdict |
|---|---|---|---|---|---|---|
| `reread_fact_lookup` | `reads_partial_reference` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `reread_edit_anchor` | `quotes_from_reference_target` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `reference_verbatim_quote` | `quotes_from_reference_target` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |

- **Exact forwarded input tokens:** 987,855 in the baseline against 594,975 in the candidate,
  39.8 % less on these cases.
- **Record:** `evals/records/reread_by_reference.yaml` (version 2).
- **Default:** as decided at Gate 1, `reread_by_reference` is **on by default** again.
- **Tests and goldens back to on:** `test_reread_on_by_default_and_declared`,
  `test_reread_by_reference_on_by_default`, `test_compressor_stats_only_for_considered`, the
  default `config_hash` and the doctor goldens.

## Known limitations

- **Thresholds.** The `not_applying` thresholds (200 considered, 50 % format reasons) are
  provisional.
- **What the fixtures prove.** They cover the shapes measured in 21 days of one developer's
  traffic. Shapes that never occurred there (for example `MultiEdit`) are not checked.

## Unresolved questions

**P5** was resolved by SCR-002 (`PowerShell` is a verbatim tool by default). The UI test of
UI-012 now reads the effective list from the configuration instead of a hard-coded one.

**Dogfood note.** The human's dashboard settings switch on `edit_args_on_resume`, whose
evaluation record is `damage_detected` (refusals). Switching it off is recommended; it is the
human's decision.

**`dictionary` and a cross-request dictionary, measured** on 21 days of the human's sessions
(counters only, line-level lower bound):
- at most 0.04 % of total cost for `dictionary`;
- at most 0.56 % for a forward dictionary across the conversation, and only when it touches
  `Read`/`Bash`, where symbols would endanger edit anchors.

The recommendation is not to build either.

## Gate 2 record

- **Date:** 2026-10-09.
- **The human's words:** "accetto s8h".
