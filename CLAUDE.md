# CLAUDE.md — How Claude works on Tokli

These rules govern **all** Claude Code work in this repository. They take precedence over habits
and defaults. Only an explicit instruction from the human in the current session overrides them,
and only for that instruction.

Tokli is a local, transparent proxy that reduces the tokens coding agents send to LLM providers
and measures, per compressor, what it saved (`TOKLI_VISION.md`). Development is
**specification-driven, test-first and human-gated**: the human approves behaviour before any code
exists, and accepts every slice before the next one starts.

## 1. Where things are

| What | Where | Status |
|---|---|---|
| Normative behaviour | `specs/NNN-*/spec.md` (EARS requirements, acceptance criteria, test scenarios) | authoritative once approved for a slice |
| Product intent, scope | `TOKLI_VISION.md`, `TOKLI_SCOPE.md` | normative for scope (SPEC 000) |
| Architecture and dependency rules | `TOKLI_ARCHITECTURE.md` (§5 is enforced by import contracts) | normative boundaries |
| Slice plan | `TOKLI_ROADMAP.md` | normative order and slice contents |
| Test categories, invariants, evaluation tiers, experiments, performance classes | `TOKLI_TEST_STRATEGY.md` | normative |
| Observability rules and per-slice checklist | `TOKLI_OBSERVABILITY.md` (§8 checklist) | normative |
| Telemetry and cost model | `TOKLI_TELEMETRY_AND_COST.md` | explanatory; normative text is in specs 008/013 |
| Requirement → test map | `TOKLI_TRACEABILITY.md` | must stay complete |
| Evidence behind the specs (hazards, measurements) | `TOKLI_EVIDENCE.md` | informative, self-contained |
| Explanation of each compressor, with examples | `TOKLI_COMPRESSORS.md` | explanatory; normative text is in specs 009/010/019 |
| Phase reviews | `PHASE0_1_REVIEW.md`, … | decision records |
| Per-slice working documents | `slices/S<n>/SPEC_REVIEW.md`, `slices/S<n>/SCR-<nnn>-<slug>.md`, `slices/S<n>/COMPLETION_REPORT.md` | created on first use |
| Architectural decision records | `docs/adr/NNNN-<slug>.md` | created on first use |

**Spec status.** A spec's `Status:` line is `Draft` until the human approves it for a slice. Claude
then records `Approved for S<n> (YYYY-MM-DD)` for the requirements in that slice. Approved
requirements change only through a Spec Change Request (§4). A spec that spans several slices is
approved slice by slice. Requirements of later slices stay `Draft`.

## 2. The slice lifecycle (mandatory, every slice)

"Stop" means: end the turn with the questions or report, and do nothing further on the slice until
the human answers. **Explicit approval** means the human clearly approves *that* gate, for example
"approved", "approvo", "go ahead with S1". Silence, a question back, partial agreement or approval
of a different gate is **not** approval. Approval of one gate never extends to the next.

1. **READ.** Read this file, the approved specs for the slice, the roadmap entry, relevant ADRs,
   `TOKLI_TEST_STRATEGY.md`, `TOKLI_OBSERVABILITY.md §8`, and the existing code and tests the slice
   touches. Write no code.
2. **SPEC REVIEW.** Create or update `slices/S<n>/SPEC_REVIEW.md` (template in §7). Identify
   ambiguities, contradictions, missing behaviour, portability concerns, observability
   requirements, architectural risks and open product decisions. Separate **product questions**
   (the human decides) from **implementation decisions** (Claude decides and records). Never
   silently resolve a material product ambiguity.
3. **HUMAN GATE 1 — spec approval.** Stop and present the material questions. When answered,
   update the specs and show the **delta** (`git diff` of the spec files). Implementation is
   forbidden until the human explicitly approves the slice. Record the approval (date and the
   human's words) at the end of `SPEC_REVIEW.md`, and set the spec status lines.
4. **FREEZE.** The approved spec is authoritative for the slice. Code conforms to the spec. A spec is
   **never** changed to make code or tests pass (§4).
5. **DERIVE TESTS.** Map every requirement and acceptance criterion of the slice to one or more
   tests that describe externally meaningful behaviour. Update `TOKLI_TRACEABILITY.md`.
6. **RED.** Write the tests first. Run them and confirm that each fails **for the expected
   behavioural reason**: an assertion on behaviour, not an import error, a missing fixture or a
   typo.
7. **GREEN.** Implement the smallest coherent production behaviour that makes the approved tests
   pass. Nothing from a later slice (§5).
8. **REFACTOR.** Only with tests green. Behaviour must not change.
9. **VERIFY.** Run every test category the slice requires (`TOKLI_TEST_STRATEGY.md §2`): unit,
   property/invariant, contract, compat, streaming, integration, regression, golden, portability.
   Do the architecture review (import contracts green; no seam without justification, §5), the
   observability checklist (`TOKLI_OBSERVABILITY.md §8`) and the portability checks the slice
   requires. Record measured performance as the slice requires (`TOKLI_TEST_STRATEGY.md §8`).
   Update traceability and docs.
10. **HUMAN GATE 2 — slice acceptance.** Write `slices/S<n>/COMPLETION_REPORT.md` (template in §7).
    Give a concise summary in chat, then stop and wait for explicit acceptance.
11. **ONLY AFTER ACCEPTANCE** is the slice complete. Record the acceptance in the report. **Never
    start the next slice automatically.** The next slice begins at step 1 only when the human asks.

Bugs found at any time: first a failing regression test named after the behaviour, with the root
cause in its docstring; then the fix. If the bug shows that the spec is wrong, use §4.

## 3. What Claude decides alone, and what needs the human

| Claude decides (and records in the SPEC_REVIEW or report) | The human decides |
|---|---|
| Internal names, module layout inside the allowed boundaries, algorithms that satisfy the spec, test structure, refactorings, private helper types | Any change to product behaviour or to an approved requirement (§4) |
| Choice between equivalent implementations | Open product questions (scope, defaults, thresholds, policy wording) |
| Adding tests beyond the required ones | Anything listed as a human gate (§2) |
| | **Significant architectural decisions** are recorded as ADRs (§6). They need human review when they also change behaviour or cross a boundary in ARCH §5. |

Always ask first, even mid-slice:

- any call that costs money or uses real credentials: provider API calls, `tokli eval`, live smoke
  tests, experiments such as E1/E2/E11 (QE-009…QE-011 apply to Claude too);
- reading real transcripts, logs or prompt content from the developer's machine (counters and
  flags only, as in E5a, and only with consent);
- commits (only when asked), any push, deleting data, changing user-level config outside the repo.

Do not ask the human about ordinary implementation details.

## 4. Specification change rule

If implementation shows that an approved requirement is wrong, incomplete, contradictory or
impractical:

- do **not** silently modify the spec;
- do **not** weaken, skip, `xfail` or delete a test;
- do **not** implement a convenient alternative.

Create `slices/S<n>/SCR-<nnn>-<slug>.md` with:

1. affected requirement(s) and acceptance criteria;
2. discovered evidence (test output, measurements, protocol facts), reproducible;
3. why the current requirement cannot or should not be implemented;
4. proposed change (exact new EARS text);
5. impact on tests;
6. impact on architecture;
7. compatibility and migration consequences (persisted schema, config keys, API, fingerprint).

Then stop and wait for approval. After approval, apply the change to the spec, traceability and
tests, and record the SCR id in the spec's change history line.

## 5. YAGNI and seams

- Implement only what the current slice's approved requirements need. No infrastructure because
  "a later slice will need it".
- `TOKLI_ARCHITECTURE.md` defines **allowed boundaries** (modules, dependency directions). It does
  not oblige Claude to build every extension point now.
- Introduce an abstraction (Protocol/ABC, registry, plugin point, config switch) only when the
  current slice requires it, **or** at least two concrete behaviours in the current code show the
  variability. Otherwise use a concrete class or function inside the right module.
- Dependency rules (ARCH §5) are enforced from S0 for the modules that exist. Contracts are added
  as modules appear.
- If an approved requirement itself asks for future-only infrastructure, raise it in the
  SPEC_REVIEW as a product question instead of building it silently.

## 6. Architectural decisions (ADRs)

Record an ADR in `docs/adr/NNNN-<slug>.md` **before** merging code that:

- creates a new dependency direction;
- introduces a persistent technology or third-party dependency;
- changes a contract relied upon by more than one module (public or internal);
- changes a persistence format (SQLite schema, files in the data dir);
- changes protocol behaviour;
- changes portability characteristics (OS, Python version, paths, encodings);
- materially constrains future implementation.

ADR content: context · decision · alternatives considered · consequences (tests, portability,
migration) · status (`proposed` / `accepted` / `superseded by NNNN`). If the ADR also changes
behaviour or an approved spec, it goes through §4 and a human gate.

## 7. Templates

**`slices/S<n>/SPEC_REVIEW.md`**
```text
# S<n> — Spec review
Slice scope (from TOKLI_ROADMAP.md) · specs and requirement IDs in scope · requirements explicitly out of scope
1. Ambiguities            (req id → question → proposed reading)
2. Contradictions         (between specs/docs, with locations)
3. Missing behaviour
4. Portability concerns
5. Observability requirements for this slice
6. Architectural risks    (incl. seams this slice would introduce, §5)
7. Product questions      → for the human (numbered, with a recommended answer)
8. Implementation decisions → decided by Claude (recorded, not asked)
9. Test plan              (req/AC → test names)
Gate 1 record: date · the human's approval words · spec delta reference
```

**`slices/S<n>/COMPLETION_REPORT.md`**
```text
# S<n> — Completion report
Requirements implemented (ids) · requirements deferred (ids, why)
Tests and evidence (commands run, counts, CI links, fixtures)
Architecture changes (modules, contracts, ADRs)
Measured performance (per TOKLI_TEST_STRATEGY §8; reported, not gated unless the spec says so)
Observability evidence (checklist §8, sample trace, reason codes)
Known limitations
Unresolved questions
Gate 2 record: date · the human's acceptance words
```

## 8. Self-contained specification

- The specification set is self-contained. A reader must be able to understand and build Tokli
  without knowing any earlier project, and no document, code, test, fixture, comment, test name or
  commit message names or depends on one.
- Evidence that the specification needs as rationale is stated in neutral, reproducible terms in
  `TOKLI_EVIDENCE.md` (hazards H##, measurements E5a) and in SPEC 018 (MD-##).
- Behaviour comes only from the specs. Where a spec is silent, that is a SPEC_REVIEW question. Do
  not fill the gap from earlier code or conventions, and never copy, vendor or import earlier code.
- All documentation is written in English, even when the conversation is in another language.

## 9. Always-on engineering rules

- **Tests:** real components in-process. Only the upstream network boundary is faked
  (`TOKLI_TEST_STRATEGY.md §2`). Fixtures are synthetic and contain no real prompts, keys,
  usernames or developer paths.
- **Privacy:** never print, log or commit credentials or prompt content. Canary strings in fixtures.
- **Portability:** Windows, Linux and macOS × CPython 3.11–3.14. No CWD-relative reads, no
  import-time I/O, explicit encodings (UTF-8), `pathlib`, CRLF-aware text handling. The development
  machine is Windows, so never assume a POSIX shell in code or tests.
- **Honesty:** report test results as they are. A skipped step is reported as skipped. Never
  claim a measurement that was not made. Unknown is "unavailable", not zero.
- **Scope:** token reduction only (`TOKLI_SCOPE.md`). No security filtering, knowledge features or
  response modification.
