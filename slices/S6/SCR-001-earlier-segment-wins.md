# S6 SCR-001 — A later reference stub must not undo an earlier segment's change

Status: **approved 2026-10-05** ("ok, basta che vinca il compressore piu' efficace": ok, as
long as the more effective compressor wins). Found by the E2 dry run of S6
(`tests/integration/test_e2_dry_run.py`).

**How the condition is met** (recorded at approval):
- **Effectiveness is judged on the money actually paid.** Keeping history already sent
  unchanged is worth more than a slightly shorter stub on a later segment: a cache read costs
  0.05–0.1× the input price, a rewrite 1.25–2×. So the earlier segment's change wins.
- **A reverted segment is offered once more to every pruner** (one extra pass, for those
  segments only). So the compressor that can still shorten it does so. In the case found, the
  second identical re-read becomes notes from `reread_by_reference` instead of going whole.
- **Section 4 includes this second pass.**

## 1. Affected requirements

| Requirement | Approved in | What it says |
|---|---|---|
| SPEC 009 **CC-019** | S4, S8e | "IF any later transformation would violate this [the target's forwarded text equals its original], THEN THE SYSTEM SHALL reject that transformation with `rejected_invariant(reference_target_modified)`." |
| SPEC 019 **PR-012** | S4 | "A later pruner that would stub or otherwise non-equivalently change that earlier result SHALL be rejected for that segment." |
| **AC-CC-10** | | "a fake SELECTIVE request compressor that stubs the target of a duplicate reference is rejected with `reference_target_modified`, and the target stays verbatim." |

**Requirements they break in combination:**
- PR-004 / PR-030: prefix stability, approved;
- the S8f principle that timing or later content must never change history already sent.

## 2. Evidence (reproducible, synthetic)

**1. The E2 dry run.** Tokli's predicted saving came out at twice the saving observed through a
simulated prompt cache (relative error 0.98, tolerance 0.25). Per request, the candidate arm's
cache read stopped growing every second request (32,313 → 32,313; 45,128 → 45,128), while the
baseline's grew each time. The candidate's history therefore changed between requests, and the
simulated provider rewrote it.

**2. The mechanism** (scratchpad check on the same conversation, engine only, budget lifted):
- **Request 2:** `reread_by_reference` accepts the re-read after an edit (segment `s8`, sent as
  notes).
- **Request 3:** the agent reads the unchanged file again (`s11`, byte-identical to `s8`'s
  original).
  1. `duplicate_tool_results` runs first by `(stage, id)`. It stubs `s11` with a reference to
     `s8`, so `s8` becomes a reference target.
  2. `reread_by_reference` on `s8` is then rejected with `reference_target_modified` (CC-019,
     PR-012).
  3. `s8` is sent whole. The forwarded history differs from request 2 from message 13 on.

**3. The regression test, failing now:**
`tests/unit/test_reread_by_reference.py::test_reread_stays_when_a_later_read_duplicates_it`.
It asserts that the forwarded history of a turn is unchanged when a later turn reads the same
file again.

## 3. Why the requirements should change

**The rule is right about integrity and wrong about precedence.**
- CC-019 must keep every reference stub pointing at an intact target. That is lossless decoding,
  and it stays.
- But it settles a conflict in favour of the **later** segment's stub. The decision about an
  earlier segment then depends on a later one, so a segment sent one way is sent another way
  once a later turn arrives.

**What that costs:**
- It is a cache rewrite of everything after that segment. Cache writes are 27.5 % of the
  developer's measured cost, and cache reads are cheap.
- It defeats the purpose of the reference compressors on exactly the traffic they target:
  agents that read a file again after editing it.
- **Where it occurs:** whenever both default-on reference compressors meet a read that is
  repeated unchanged after an edit-and-reread.
  - Claude Code usually answers an unchanged re-read with a short "file unchanged" note, so the
    pattern is rarer there.
  - It occurs as soon as an agent sends the full content again.

## 4. Proposed change (exact EARS)

**CC-019** becomes:

> CC-019 | WHILE a reference stub is part of the forwarded request, THE SYSTEM SHALL ensure that
> the named target segment precedes the stub in the same request and that the target's
> forwarded text equals its original text under byte or structural equivalence. THE decision
> for a segment SHALL NOT depend on a later segment: WHEN a transformation of a segment
> conflicts with an accepted reference stub on a later segment that names it, THE SYSTEM SHALL
> keep the transformation and SHALL revert that stub (the stubbed segment keeps its text from
> before the stub), recording
> `rejected_invariant(reference_target_changed)` for the stub. IF a stub would name a target
> that is already changed, THEN THE SYSTEM SHALL reject the stub with
> `rejected_invariant(reference_target_modified)`. THE SYSTEM SHALL offer a reverted segment
> once more to every request-scope compressor, in chain order, and then to the segment-scope
> compressors, so that another compressor may still shorten it. These checks SHALL always run,
> independent of `verify_lossless`. (S6 SCR-001.)

**PR-012**, last sentence becomes:

> A transformation of that earlier result by a later pruner or compressor SHALL be kept, and the
> stub SHALL be reverted (CC-019). (S6 SCR-001.)

**AC-CC-10** becomes:

> AC-CC-10 (CC-019): a fake SELECTIVE request compressor that changes the target of a duplicate
> reference is accepted, and the duplicate stub is reverted with `reference_target_changed`, so
> that no stub points at a changed target. A fake structural compressor that changes the target
> is accepted and the stub stays, and the trace records the chain guarantee as `structural`. A
> stub whose target was changed earlier in the chain is rejected with
> `reference_target_modified`.

**New acceptance criterion:**

> AC-CC-16 (CC-019, PR-004): over a growing conversation in which an edited file is read again
> twice with the same content, the forwarded history of each request is byte-identical in the
> next request, with `duplicate_tool_results` and `reread_by_reference` both enabled.

**Effect in the scenario above:**
- the earlier re-read keeps its notes;
- the duplicate stub on the second re-read is reverted;
- in the second pass `reread_by_reference` turns the second re-read into notes too, from the
  original first read.

No history already sent changes, and both re-reads stay compressed.

## 5. Impact on tests

| Test | Change |
|---|---|
| `test_reference_target_integrity_enforced` (AC-CC-10) | Rewritten as above |
| `test_reread_stays_when_a_later_read_duplicates_it` | New regression test, failing now |
| `test_history_stays_stable_with_both_reference_compressors` (AC-CC-16) | New property test over random read / edit / re-read sequences |
| `test_e2_dry_run_self_test` | Unchanged; expected to pass after the fix |
| Duplicate-pruning tests that rely on rejecting a later change to a target | Reviewed: their assertions change only where they encode the old precedence |

## 6. Impact on architecture

- **Engine only** (`tokli.compression.engine`):
  - the reference-target bookkeeping gains "revert the later stub";
  - a reverted segment is again open to later compressors in the chain.
- **No new module, dependency or seam.** The compressor contract is unchanged.

## 7. Compatibility and migration

- **No change to:** persisted schema, config keys, `config_hash` or compressor versions. The
  compressors are unchanged; the engine's arbitration changes.
- **New reason code:** `reference_target_changed` (TOKLI_OBSERVABILITY §4 gains it).
- **One-time cache rewrite.** Forwarded bytes change for requests that hit the conflict. A user
  upgrading mid-session sees one cache rewrite, as for any Tokli update that changes output.
- **The smoke records of both compressors stay valid.** Their outputs per segment are the same
  transformations, only arbitrated differently.
