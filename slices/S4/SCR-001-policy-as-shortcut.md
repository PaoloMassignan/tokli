# S4 SCR-001 — The policy is a shortcut, not a gate

Slice: S4 · Status: **approved 2026-10-03** with S4 Gate 1 ("Approvo s4") · Date: 2026-10-03

## 1. Affected requirements

- **SPEC 009:** CC-002 (approved for S1, then with the fixed LOSSLESS_ONLY policy), AC-CC-1,
  AC-CC-11, and the "policy eligibility" column of the preservation-model table.
- **SPEC 010:** the "LOSSLESS_ONLY" column of the catalogue.
- **SPEC 012:** QE-012 (the candidate arm's policy).
- **SPEC 015:** the editable keys of `PATCH /tokli/api/config`, AC-API-3.
- **SPEC 016:** UI-004, UI-010, the Settings and Overview rows.
- **SPEC 017:** CF-009, the precedence examples, AC-CF-1, AC-CF-2.
- **SPEC 019:** the LOSSLESS_ONLY / LOSSY_ALLOWED mentions in the purpose and in AC-PR-5,
  AC-PR-7 and AC-PR-8.

## 2. Evidence

The product owner's answer at S4 Gate 1 (2026-10-03): "Sulla ui è possibile scegliere se attivare
o no un compressore. Lossy/lossless è solo una scorciatoia". In English: in the UI you choose
whether each compressor is on or off; lossy/lossless is only a shortcut. The spec made the policy a
second gate: under LOSSLESS_ONLY, an enabled non-lossless compressor would silently not run.

## 3. Why the current requirement should not be implemented

Two switches for one decision confuse the user: a compressor shown "on" may not run. The
safety the gate gave is already provided by other rules:
- non-LOSSLESS compressors are never enabled by default (CC-002, new text);
- default enablement needs an evaluation record (CC-020);
- each compressor shows its kind.

## 4. Proposed change

- **CC-002 (new text).** A compressor runs when it is enabled and available. Its kind and
  equivalence never gate execution and are shown with it. Non-LOSSLESS compressors are never
  enabled by default. The dashboard offers "Lossless only", which switches off every enabled
  non-LOSSLESS compressor in one change. The request's `policy` field is derived:
  `LOSSLESS_ONLY` when every enabled compressor is LOSSLESS, else `LOSSY_ALLOWED`.
- **No `compression.policy` key and no `--policy` flag.** The UI-editable keys are
  `compressors.<id>.enabled` and `telemetry.retention_days`.
- **UI-004 and UI-010** describe the toggles, the shortcut and the meaning of the kinds.
- **The reason code `policy_forbids(kind)`** is no longer produced; it is removed from the closed
  set.
- The other affected texts are reworded accordingly; the exact delta is in `git diff` at Gate 1.

## 5. Impact on tests

- AC-CC-1 is reworded: disabled fakes are not called, enabled ones are, and the policy field is
  derived. `test_lossless_only_never_runs_lossy_compressor` becomes
  `test_non_lossless_compressors_run_only_when_enabled`.
- New tests: `test_policy_field_derived_from_enabled_kinds` and
  `test_ui_lossless_only_shortcut_switches_off_non_lossless`.

## 6. Impact on architecture

- **Simpler engine:** the policy filter goes away.
- **No new key.**

## 7. Compatibility and migration

- **Telemetry:** the persisted `policy` column keeps its values. They now mean "the enabled set
  was lossless-only".
- **Config:** no config key existed for the policy, so nothing migrates.
- **Fingerprint:** `config_hash` is unchanged for the same enabled set.
