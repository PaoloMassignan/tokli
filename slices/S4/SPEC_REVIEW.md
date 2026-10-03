# S4 — Spec review

Slice: **S4 — Compressor registry, policy and configuration API** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-10-03.** Implementation in progress.

## Scope

**Roadmap content.**
- The global policy LOSSLESS_ONLY / LOSSY_ALLOWED (CC-002) and per-compressor enable (CC-003).
- `ConfigService` and `/tokli/api/config`, with the UI-override layer, locked-key reporting and
  Origin checks (CF-001, CF-009, API-005…API-007).
- UI toggles, the policy switch, and compressor cards from registry metadata.
- The second LOSSLESS compressor, **`duplicate_tool_results`** (SPEC 019; request scope,
  reference equivalence, prefix-stable), with `ToolRecord`s (CM-013), chaining before segment
  compressors, reference integrity (CC-019) and marginal attribution.
- Case families `reference_fact_lookup` and `reference_verbatim_quote`. **Default-enabled only if
  its smoke record says `no_measurable_damage` (E11)**; otherwise it ships available but off.

Exit: toggling a compressor in the UI changes the next request's `config_hash` and attribution,
and the dashboard shows pruning and text-compression savings separately.

**Requirements in scope (proposed):**

| Spec | In S4 | Deferred (slice) |
|---|---|---|
| 001 canonical model | CM-013 (`ToolRecord`, Anthropic) | OpenAI parts (S5/S7) |
| 009 compression core | CC-002 (switchable), CC-003, CC-009 (chains, terminal), CC-015 (reference), CC-016 (reference decode), CC-019, CC-021, the request scope | CC-018 (first non-prefix-stable compressor, S8) |
| 010 compressors | `duplicate_tool_results` entry; assumptions `resolves_result_reference`, `quotes_from_reference_target` | the S8 compressors |
| 019 pruning | PR-001…PR-005, PR-009 (flag stays false: duplicates never rewrite history), PR-010…PR-013 | PR-006, PR-007, PR-008, PR-014 (`analyze.tool_resources`, `superseded_tool_results`, shell classification: S8) |
| 012 evaluation | families `reference_fact_lookup`, `reference_verbatim_quote`; the candidate arm's policy LOSSY_ALLOWED (QE-012, now possible) | full tier (S8) |
| 013 telemetry | TC-014 `reference_stubs` filled; savings by scope (P10) | cost (S6) |
| 015 API | `GET`/`PATCH /tokli/api/config`, `GET /tokli/api/compressors` with `locked_by` and evaluation status; API-005, API-006, API-007 | diagnostics (S9) |
| 016 dashboard | Settings page, toggles, policy switch; UI-003 (evaluation status), UI-004, UI-005, UI-010, AC-UI-3 | diagnostics page (S9), debug banner (OB-009) |
| 017 configuration | CF-001 layer 5 (UI overrides), CF-002 (`ui` source), CF-009; new keys (P2, P12) | — |

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | PR-002 | A tool result can hold several text blocks (several segments). What does "identical to the result of tool call X" mean when X had more than one block? | Duplicates are considered only when the stubbed result **and** the target are each a single text segment (the whole result). Multi-block results are left alone. See P7. |
| A2 | PR-002, CC-007 | Claude Code appends `<system-reminder>` blocks inside tool results. A stub that replaces the whole text would remove a protected span, so the engine would reject every such stub. | The stub keeps every protected span of the replaced text verbatim, in order, after the stub line. The decoder restores the original from the target. See P6. |
| A3 | CF-009, API-007 | What happens to a running request when the configuration changes? | A PATCH builds a new snapshot (config, pipeline, engine) and swaps it atomically. A request uses the snapshot it started with (CF-005, AC-API-5). Tokenizers are reused, not reloaded. |
| A4 | PR-002 | Is "byte-identical original text" compared before or after other transformations? | On the original text of the segments (the client's bytes), before any compressor. Request-scope compressors run first (PR-010). |
| A5 | TC-014 | What does `reference_stubs` count? | The number of segments replaced by an accepted reference stub in the forwarded request. |
| A6 | UI-003 | Where does the evaluation status come from at run time? | See P5. |

## 2. Contradictions

| Id | Where | Contradiction | Proposed resolution |
|---|---|---|---|
| X1 | SPEC 017: precedence list ("5. UI overrides", highest) and AC-CF-1 ("file < env < CLI < UI") vs. its rationale ("UI above file but below env/CLI"; "only … not pinned by layers 3–4") | AC-CF-1 says a UI value beats the CLI. The rationale and the "not pinned" rule say it never does. | The rationale is the rule: a UI override applies only to a `ui_editable` key that env/CLI do not set; it beats defaults and the file. AC-CF-1 is reworded: "file < UI (when editable and not pinned); env/CLI always win, and PATCH on a pinned key is 409 (API-005)". |
| X2 | QE-012 vs. S2.5 SCR-001 / reading A1 of S2.5 | The candidate arm should run under LOSSY_ALLOWED. S2.5 had no policy switch, so it used LOSSLESS_ONLY. | Now that the switch exists, both arms use LOSSY_ALLOWED as QE-012 says. Both compressors evaluated so far are LOSSLESS, so earlier records stay valid. |
| X3 | SPEC 012 family `reference_verbatim_quote` ("exact substring of the file") vs. QE-020 (only two checkers) | The family needs a checker that QE-020 does not define. | A third checker, `verbatim_line`, added to QE-020. See P9. |

## 3. Missing behaviour

- **M1. The policy key.** `compression.policy` (`LOSSLESS_ONLY` / `LOSSY_ALLOWED`, default
  `LOSSLESS_ONLY`) and the named flag `--policy` are referenced by SPEC 017 but not in its key
  tables.
- **M2. Pruning keys.** SPEC 019 names `pruning.duplicate_min_tokens` (64) and
  `pruning.duplicate_require_same_call` (false); they are added to SPEC 017 ("Keys added in S4").
- **M3. Persistence of UI overrides.** API-007 says `<data>/ui-overrides.yaml`. It is written
  atomically (temporary file, then rename), read strictly at startup like the config file, and
  shown as source `ui`.
- **M4. A PATCH that changes nothing** (same value) answers 200 with the unchanged
  `config_hash`.
- **M5. Mutations without an `Origin` header** (curl, scripts): API-006 rejects only a present,
  foreign `Origin`. The Host check (API-009) applies to all `/tokli/*` requests.

## 4. Portability concerns

- **Atomic file replace on Windows:** `os.replace` is atomic on NTFS and fails if another process
  holds the target open. A failed write answers 500 and leaves the previous overrides in place.
- **Stub text** is ASCII plus the em dash already defined by SPEC 019. It is rendered as UTF-8
  everywhere, and the golden tests compare bytes on all OSes.

## 5. Observability requirements for this slice

- **Trace:** request-scope stage spans, each proposal's decision (accepted, rejected with reason,
  including `reference_target_modified`), the chain per segment, and `reference_stubs`.
- **Reason codes:** existing ones only (`rejected_invariant(reference_target_modified)` is already
  in the closed set).
- **Config changes:** one INFO log line per accepted PATCH (keys and new `config_hash`, never
  values of non-editable keys); the new hash appears on the next request's record.
- **Credential and content scans** extended to stubs (no content beyond the stub template, call
  ids and protected spans) and to the config API.

## 6. Architectural risks

- **R1. Swapping the runtime.** Today the proxy holds one `Services`. A `Runtime` holder in
  `tokli.app` (current snapshot, swapped under a lock) gives every request a consistent view
  (CF-005). The HTTP layer reads `runtime.current()` once per request.
- **R2. Engine request scope.** A second compressor protocol (`RequestCompressor.plan` →
  proposals) is justified by two concrete behaviours (CLAUDE.md §5). Proposals reuse the
  segment acceptance gate.
- **R3. Reference integrity** must be checked for every later change to a target, including the
  result cache's hits (CC-024): the check runs after the cache, on the output.
- **R4. ADRs.**
  - ADR 0009: runtime configuration changes (snapshot swap, UI-override file).
  - ADR 0010: the request-scope compressor contract and reference integrity.
  - Packaging of evaluation records (P5) is part of ADR 0009.
- **Seams introduced:** `RequestCompressor` (two behaviours: segment and request scope). Nothing
  else.

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **Pruning scope in S4:** only `duplicate_tool_results`. The tool-semantics analyzer, `superseded_tool_results` and the shell rules (PR-006/007/008/014) stay in S8 as planned. | Yes. |
| **P2** | **Policy key and flag:** `compression.policy` (default `LOSSLESS_ONLY`), `--policy`, UI-editable. | Yes. |
| **P3** | **What the UI may change in v1:** the policy, each compressor on/off, `telemetry.retention_days` (CF-009). Changes apply to the next request; requests in flight keep the old snapshot. | Yes. |
| **P4** | **UI-override precedence (X1):** UI values beat the file and the defaults, never env/CLI; a key set by env/CLI is shown locked with its source. | Yes. |
| **P5** | **Evaluation status in the UI (UI-003):** the build copies `evals/records/*.yaml` into the package (read-only data), so a running Tokli can show "smoke · no measurable damage · claude-opus-5-5 · 2026-10-03" next to each compressor. A record whose version differs from the compressor's is shown as "outdated". | Yes. |
| **P6** | **Stubs keep the reminders (A2):** the stub line, then every `<system-reminder>` (protected span) of the replaced result, verbatim. Without this, Claude Code's `Read` results, which carry a reminder, could never be pruned. | Yes. |
| **P7** | **Single-block results only (A1)** for both the target and the stub, in S4. | Yes. |
| **P8** | **E11, the real evaluation of `duplicate_tool_results`.** You run it, as in S2.5: 2 new families × 22 cases × 3 repetitions × 2 arms ≈ 264 calls on `claude-opus-5-5`. The requests are multi-turn, so they are larger than the JSON cases: the plan shows the estimated tokens before you confirm. The verdict decides `default_enabled`. | Yes. |
| **P9** | **Checker `verbatim_line` (X3)** for `reference_verbatim_quote`: the task asks for the exact line of a file that contains a given marker (an "edit anchor"). The answer's last non-empty line, trimmed of surrounding quotes or backticks, must equal that line of the file **byte for byte**, leading whitespace included. | Yes. |
| **P10** | **Savings split on the dashboard (exit criterion):** the summary gains `saved_by_scope` (`request` = pruning, `segment` = text compression), each a token figure with its method. The Overview shows both. | Yes. |
| **P11** | **Q17 (stub wording):** keep SPEC 019's stub ("identical to the result of tool call <id> earlier in this conversation — <n> tokens omitted") for E11. Naming the tool and the resource would need the tool-semantics analyzer (S8). | Keep the wording; revisit if E11 shows damage. |
| **P12** | **Scope readings** (the table above, A1–A6, X1–X3, M1–M5). | Accept as proposed. |

## 8. Implementation decisions (decided by Claude, recorded)

- **I1. `ToolRecord`** (CM-013) is built by the Anthropic adapter from `tool_use` blocks:
  - fields: call id, name, arguments as parsed JSON, index;
  - result segment ids: from the matching `tool_result`.
- **I2. Engine.**
  - Request-scope compressors run first, ordered by `(stage, id)`. Each proposal passes the same
    filters (policy, enabled, availability, budget) and the same gate (token non-increase,
    protected spans, min gain), and is attributed to its compressor.
  - Segment-scope compressors then run on the resulting texts. A stubbed segment is not
    JSON-like, so `json_minify` skips it naturally.
- **I3. Reference integrity (CC-019).** The engine keeps a map target → stubs. A later change to
  a target is accepted only from a compressor with equivalence `byte` or `structural`; otherwise
  it is `rejected_invariant(reference_target_modified)`. A stub never names a stub.
- **I4. Decode.** `decode_request` replaces each stub with the target's original text plus nothing
  else: the protected spans kept in the stub are those of the original, which the target also
  holds. The property test decodes the whole request and compares it with the original texts.
- **I5. Prefix stability.** The plan for segment j reads only segments 0…j. A test runs turn N and
  turn N+1 and compares the shared prefix byte for byte.
- **I6. `Runtime`** in `tokli.app.runtime`: `current()`, `apply(changes)`. `ConfigService` in
  `tokli.app.config_service` validates PATCHes against `ui_editable` and pinning (API-005),
  writes `ui-overrides.yaml`, builds the new snapshot and returns the effective config.
- **I7. UI.** A Settings tab with:
  - the policy switch, with the UI-010 texts;
  - compressor cards (kind and equivalence, assumptions, evaluation status, availability, toggle,
    lock with its source);
  - non-LOSSLESS toggles marked "not permitted by policy" under LOSSLESS_ONLY (UI-004).

  The Overview shows savings by scope (P10).
- **I8. Cases.** `evals/make_cases.py` gains the two reference families:
  - multi-turn histories with a repeated non-verbatim and a repeated `Read` result;
  - the question about the later read;
  - the stubbed segment is the later one.

## 9. Test plan

| Requirement / AC | Tests |
|---|---|
| CM-013 | `test_tool_records_exposed_read_only` |
| PR-002/003, AC-PR-1 | `test_duplicate_results_stub_later_copies`, `test_duplicate_pruning_never_stubs_first_occurrence`, `test_duplicate_stub_names_earliest_copy`, `prop_duplicate_pruning_decodes_whole_request` |
| PR-004, AC-PR-2 | `test_duplicate_pruning_prefix_stable_across_turns` |
| PR-005, AC-PR-3 | `test_pruning_preserves_structure_and_arguments` (all compat fixtures) |
| PR-010 | `test_pruning_runs_before_segment_compressors` |
| PR-011 | `test_stub_preserves_cache_control_and_is_error` |
| PR-012, CC-019, AC-CC-10 | `test_reference_target_integrity_enforced` |
| PR-013, CC-021, AC-CC-12, AC-PR-9 | `test_duplicate_pruning_applies_to_verbatim_tools` |
| A1, A2 (P6, P7) | `test_duplicate_stub_keeps_protected_spans`, `test_multi_block_results_not_pruned` |
| `duplicate_require_same_call` | `test_duplicate_require_same_call_option` |
| CC-002, AC-CC-1, AC-PR-7 | `test_lossless_only_never_runs_lossy_compressor` (with the pruner registered), `test_lossy_allowed_runs_selective_and_lossy` |
| CC-009 | `test_terminal_stops_chain`, `test_chain_order_by_stage_then_id` |
| TC-003, TC-014 | `prop_marginal_savings_sum_to_total` (with pruning), `test_reference_stubs_counted` |
| CF-001, CF-002, CF-009 | `test_ui_override_only_when_not_pinned`, `test_config_show_reports_sources` (UI source) |
| API-005…API-007, AC-API-3…5 | `test_patch_pinned_key_conflict`, `test_patch_unknown_key_rejected`, `test_mutation_rejects_foreign_origin`, `test_config_change_atomic_snapshot` |
| UI-003…UI-005, UI-010, AC-UI-3 | `test_ui_toggle_patches_config`, `test_ui_policy_marks_non_lossless_not_permitted`, `test_ui_locked_settings_show_source`, `test_ui_policy_explanations_text`, `test_ui_shows_equivalence_assumptions_and_eval_status` |
| P5 | `test_wheel_contains_eval_records`, `test_outdated_record_shown_as_outdated` |
| P10 | `test_summary_savings_by_scope` |
| QE (families, P9) | `test_checker_verbatim_line`, `test_eval_cases_lint` (new families), `test_smoke_harness_self_test` (with the pruner) |
| Exit | `test_ui_toggle_changes_next_config_hash_and_attribution` (browser); the human's E11 run and dogfood check |

Answers 2026-10-03: "Si confermo con un paio di note. Sulla ui è possibile scegliere se attivare o
no un compressore. Losst/lossoess è solo una scorciatoia. Poi vedo il risparmio per compressore".
P1, P3–P9, P11, P12 accepted as recommended. Two changes from the notes:
- **P2 is replaced by S4 SCR-001**: enabling a compressor is the only control; "Lossless only" is
  a shortcut that switches off non-lossless compressors; there is no `compression.policy` key or
  `--policy` flag; the request's `policy` field is derived.
- **P10 becomes savings per compressor**: the Overview shows each compressor's saved tokens with
  their method (from `metrics/compressors`), which also separates pruning from text compression.
  No `saved_by_scope` field.

Spec delta (uncommitted): SPEC 009 (CC-002, AC-CC-1, AC-CC-11, table), 010 (catalogue column),
012 (QE-012), 015 (PATCH keys, AC-API-3), 016 (UI-004, UI-010, Settings, Overview), 017 (precedence
X1, CF-009, AC-CF-1, AC-CF-2, keys added in S4), 019 (policy mentions), TOKLI_OBSERVABILITY §4
(`policy_forbids` removed), TOKLI_TELEMETRY_AND_COST §2 (`policy` derived), TOKLI_ROADMAP.
SCR: `slices/S4/SCR-001-policy-as-shortcut.md`.

Gate 1 record: **approved 2026-10-03**, the human's words: "Approvo s4". The approved readings P6,
P7, P9, A3–A5 and M3–M4 were written into SPEC 019 (PR-015), SPEC 012 (QE-020 `verbatim_line`) and
SPEC 015 (API-007) right after the approval. Status lines set in SPEC 001, 009, 010, 012, 013, 015,
016, 017 and 019.
