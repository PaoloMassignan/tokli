# Tokli

**Status: specification approved (Phase 0.1). Current slice: S0 (`slices/S0/`). Licence: Apache-2.0.**

Tokli is a local, transparent proxy that reduces the tokens and cost that coding agents (Claude
Code, Codex, SDK clients) send to Anthropic and OpenAI. It proves how much it saved and which
compressor saved it, and it never trades task quality for a bigger number.

## Reading order

1. `TOKLI_VISION.md`, `TOKLI_SCOPE.md`: what Tokli is and is not.
2. `TOKLI_COMPRESSORS.md`: every compressor explained one by one, with examples.
3. `TOKLI_ARCHITECTURE.md`: modules, canonical model, seams, dependency rules, self-attack review.
4. `TOKLI_ROADMAP.md`: vertical slices S0–S9 (plus S2.5); S1 is the first useful slice.
5. `specs/000…019`: normative requirements (EARS), acceptance criteria, test scenarios.
6. `TOKLI_TEST_STRATEGY.md`: test categories, invariants, evaluation tiers, experiments E1–E11,
   performance classes.
7. `TOKLI_TELEMETRY_AND_COST.md`, `TOKLI_OBSERVABILITY.md`.
8. `TOKLI_EVIDENCE.md`: the hazards and measurements the specification rests on.
9. `TOKLI_TRACEABILITY.md`: evidence → requirement → spec → acceptance criterion → test.
10. `PHASE0_1_REVIEW.md`: Phase 0.1 decisions.
11. `CLAUDE.md`: the binding, human-gated development process for every slice.

Spec map: 000 scope · 001 canonical model · 002 transparent proxy · 003 Anthropic ·
004 OpenAI Chat · 005 OpenAI Responses · 006 upstream & auth · 007 pipeline & seams ·
008 token measurement · 009 compression core · 010 v1 compressors · 011 routing ·
012 quality evaluation · 013 telemetry & cost · 014 observability · 015 application API ·
016 dashboard · 017 configuration · 018 portability & diagnostics · 019 tool-history pruning.

## Development

Requires CPython 3.11, 3.12 or 3.13.

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
tokli setup tokenizers                            # downloads and verifies the tokenizer files
tokli doctor
tokli serve                                       # http://127.0.0.1:8787/anthropic
pytest && ruff check . && mypy && lint-imports
```

The process for every change is in `CLAUDE.md`. Per-slice records are in `slices/`, and
architectural decisions are in `docs/adr/`.

## Largest technical risks

| # | Risk | Why it matters | Mitigation / decider |
|---|---|---|---|
| R1 | **Verbatim-quoting hazard** (H04). Agents copy tool output back (edit anchors, JSON arguments). Any transformation, even a lossless one, can break tool calls. | Quality loss that token metrics cannot see | `verbatim_tools` exclusion, tool-result scope only, evaluated assumptions, **E8**, **E11** |
| R2 | **Prompt-cache economics** (H05, H22). Most agent input is cache reads (~10 % of the input price), so real savings may be small. A config change mid-session re-writes the cache (~1.25×). | "Savings" could be overstated or even negative | Determinism (CC-006), proportional cost with bounds, **E2** |
| R3 | **Little lossless-compressible content.** Tool outputs are mostly source files, which are verbatim-hazardous. E5a measured 8.1 % text-compression saving, mostly from lossy transformations (TOKLI_EVIDENCE §2). | LOSSLESS ONLY will likely save low single-digit % from text compression | No savings target before E5b. Duplicate pruning (SPEC 019). Selective compressors behind LOSSY ALLOWED plus user-run evaluations (SPEC 012). |
| R4 | **OAuth/subscription passthrough** may be technically fragile | Claude Pro/Max users are a key audience | Accepted by the product owner (Q8). **E1** verifies that it works. |
| R5 | **Tokenizer mismatch** for Claude (no public tokenizer) | Gate decisions and attribution are estimates | Calibration `k`, outlier handling, **E3** |
| R6 | **Streaming correctness** under passive usage parsing across three protocols | Any regression breaks the client | Byte-identity and timing tests, bounded parser, **E4** |
| R7 | **Evaluation cost and validity** | Without it, no default can be justified | Smoke tier in S2.5, full tier in S8. Each user decides their own budget per run (Q11). |
| R8 | **Latency.** Whole-conversation compression measured ~1 s per request (E5a). | Overhead users feel directly | Measured from S1 (E9, TC-013); runtime budget CC-014; cheap-first routing. The 25 ms figure is a target, not a gate (TOKLI_TEST_STRATEGY §8). |

## Unresolved questions

| ID | Question | Owner / resolver |
|---|---|---|
| Q1 | Expose `system` and tool descriptions as mutable in v1? (Proposed: no.) | E2 + E5 |
| Q2 | ~~Path prefix in `ANTHROPIC_BASE_URL`?~~ | **Resolved 2026-10-02 (E1):** accepted. |
| Q3 | ~~Current Anthropic SSE usage fields~~ | **Resolved 2026-10-03 (E4):** `message_delta` repeats input usage cumulatively, without the 5m/1h split (SPEC 003). |
| Q4 | Compress `count_tokens` bodies so the client's context accounting matches what is sent? | Product decision |
| Q5 | Chat-compatible providers with usage in every chunk: take the last value? | Proposed yes |
| Q6 | ChatGPT-subscription Codex upstream feasibility | E6 |
| Q7 | ~~Bundle tokenizer files?~~ | **Resolved 2026-09-29:** no; `tokli setup tokenizers` with pinned SHA-256 (TM-010). |
| Q8 | ~~Proxying subscription OAuth traffic~~ | **Resolved 2026-09-28:** accepted. Only technical verification (E1) remains. |
| Q9 | Per-compressor vs global `min_gain_ratio` | S4 data |
| Q10 | Use historical effectiveness to tune routing? (Deferred.) | Post-v1 spec |
| Q11 | ~~Budget for Tier 2/3 evaluation~~ | **Resolved 2026-09-28:** the Tokli user decides per run (QE-009…QE-011). |
| Q12 | Consented, scrubbed real transcripts for evaluation realism? | Product owner |
| Q13 | ~~Where Tokli lives~~ | **Resolved 2026-09-28:** this repository. |
| Q14 | How much of the E5a pruning saving came from tool-call arguments rather than results? | E5b |
| Q15 | Do APIs and models accept stubbed historical arguments / removed pairs? | E10 |
| Q16 | Cache cost vs saving of superseding | E2-ext |
| Q17 | Should the duplicate stub also name the tool and resource? | E11 |
| Q18 | ~~Smoke-tier thresholds~~ | **Resolved 2026-09-29:** n ≥ 20 per assumption, `b − c ≤ 1`, 3 repetitions (QE-015). |
| Q19 | ~~Reference model for smoke runs~~ | **Resolved 2026-09-29:** the Claude model used for dogfood; one model until S8. |

## First slice (S1)

Anthropic Messages through Tokli with passthrough auth and one provably lossless compressor
(`json_minify`), fully observable. It is preceded by S0 (skeleton, configuration, tokenizer
provisioning, doctor). Details: `TOKLI_ROADMAP.md`.
