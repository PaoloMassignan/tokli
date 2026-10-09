# S8h — Spec review

## Slice scope

- **Fix.** `reread_by_reference` must accept Claude Code's real `Read` numbering
  (`SCR-001-claude-code-read-numbering.md`).
- **Robustness,** asked by the human on 2026-10-09 ("rendi robusto questo tipo di cose": make
  this kind of thing robust). A compressor whose assumptions about the agent's output are wrong
  must be caught before release, and on the dashboard the same day if it slips through.

## What went wrong, as a class

**A compressor was specified, tested and evaluated only on synthetic input that we wrote
ourselves.**
- Every test passed and the smoke record said `no_measurable_damage`.
- On real traffic the compressor never acted.
- Nothing in the product noticed: it reported `not_applicable` 1,627 times, which looks like
  normal operation.

**Three gaps:**
1. **No real-format check before release.** Fixtures copy the formats we believed the agent
   sends.
2. **No alarm for a default-on compressor that never applies.** The dashboard flags "latency
   without benefit" (TC-016), but not "never applies".
3. **No process step that asks "does it fire on real traffic?"** before Gate 2.

## 7. Product questions (for the human)

**P1. Smoke record after the fix** (SCR-001 §4). Recommended: **(a)** regenerate the reread
families in Claude Code's real numbering and rerun the smoke evaluation (you run it).

**P2. Format fixtures from real traffic, content-free.**
- **What:** a test fixture set that records the **shape** of each agent output Tokli relies on,
  with synthetic content:
  - `Read` numbering;
  - the `Write`/`Edit` argument names;
  - Bash result layout;
  - error results;
  - system-reminder blocks.
- **How it is made:** shapes are extracted from your sessions, with consent, as counters and
  patterns only. No real line is stored.
- **What it guards:** every compressor with a format assumption is tested against these
  fixtures, and a contract test fails when a compressor declares a format no fixture covers.
- **Recommended: yes.**

**P3. A "never applies" flag.**
- **The rule:**
  - a default-on compressor considered at least 200 times in the range, with 0 % applicable; or
  - a compressor whose top skip reason is a format reason (`nonstandard_numbering`, `not_json`,
    …) above 50 % of its considered calls.
- **What you see:** the Compressors page and `/tokli/health` flag it as "does not apply to your
  traffic", with that skip reason, next to "latency without benefit".
- **Thresholds:** POLICY, provisional.
- **Recommended: yes.** This one alone would have shown the defect on the first day of dogfood.

**P4. A real-traffic check in the slice process** (`CLAUDE.md` §2, `TOKLI_TEST_STRATEGY.md`).
- **The rule:** before Gate 2 of any slice that adds or changes a compressor, run an **offline
  replay**:
  - the human's recent agent sessions go through the new pipeline locally;
  - nothing is sent anywhere;
  - only counters are printed: how often the compressor was considered, was applicable and was
    accepted, its skip reasons, and the tokens saved.
- **Where it goes:** it becomes a tool in the repository (`python -m tools.replay`, consent
  asked each run), instead of ad-hoc scripts.
- **The completion report** records the result. A default-on compressor with 0 % applicable on
  real traffic cannot pass Gate 2 without the human's explicit decision.
- **Recommended: yes.**

## 8. Implementation decisions (Claude)

- **Recording the numbering style.** The style is part of the parsed block (`padded6` or `plain`),
  and the pruner verifies its own decode before proposing. That guarantees PR-034 for both
  styles.
- **Where the replay lives.** It reuses the real pipeline (parse, pipeline, engine) on requests
  rebuilt from session files. It writes nothing, and its output is aggregates only.

## Gate 1 record

- **Date:** 2026-10-09.
- **The human's words:** "approvo", for SCR-001 and P1–P4 as recommended.
- **Implementation decision recorded at Gate 1:** `reread_by_reference` goes to version 2, and
  its evaluation record is for version 1. Until the human reruns the smoke evaluation (P1), the
  compressor is **off by default** (CC-020), as in S8e. It goes back on with the version 2
  record.
- **Spec delta:**
  - SPEC 019: PR-030 (default), PR-032, AC-PR-22;
  - SPEC 013: TC-021;
  - SPEC 016: UI-014;
  - SPEC 014: OB-011;
  - `TOKLI_TEST_STRATEGY.md` §2 and `CLAUDE.md` §2 / §7 (real-traffic replay);
  - ADR 0013 amendment;
  - all of it in the S8h commit.
