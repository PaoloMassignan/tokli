# SCR-001 — Temperature cannot be set on the dogfood model

Slice: S2.5 · Status: **approved 2026-10-03** ("approvo SCR-001"), applied to SPEC 012 · Date: 2026-10-03

## 1. Affected requirements

- **QE-012:** "Both arms use the real pipeline, the same model and parameters, temperature 0, …".
- **QE-003:** "≥ 3 repetitions at temperature 0" (full tier, S8). Same issue, same fix.
- AC-QE-5 and the smoke report (QE-014) are unaffected, except that the report must state the
  temperature used.

## 2. Evidence

The real smoke run of `json_minify` on `claude-opus-5-5` (the dogfood model, decision P1 / Q19),
2026-10-03, second attempt. Every call was rejected before any token was processed:

```text
stopped after 10 consecutive errors: the run cannot judge the compressor
  errors: 10 x invalid_request_error: `temperature` is deprecated for this model.
```

The first attempt (264 calls) failed the same way. That attempt also exposed two harness bugs
that are now fixed with regression tests (commit c685bea):

- an all-error run gave a verdict;
- the provider's message was not recorded.

## 3. Why the current requirement cannot be implemented

The provider rejects any request to this model that carries `temperature`. A run at
temperature 0 is therefore impossible on the model that Q19 chose, and on any model with the
same rule.

## 4. Proposed change (new EARS text)

QE-012, replacing "temperature 0" with:

> … the same model and parameters, and `--temperature` (default `0`). WHEN `--temperature default`
> is given, THE harness SHALL send no `temperature` parameter in either arm. THE report SHALL
> state the temperature used ("0" or "model default"). Repetitions and the majority rule of
> QE-015 absorb sampling variation.

QE-003 (S8): "≥ 3 repetitions at temperature 0, or with the model's default temperature where the
model does not accept one (QE-012)".

The choice is explicit, on the command line. The harness never guesses from the provider's error
text. Both arms always use the same setting, so the comparison stays fair.

## 5. Impact on tests

- **New test:** `test_eval_temperature_default_omits_the_parameter`. With
  `--temperature default`, no request body contains `temperature`. The report says
  "model default".
- **Unchanged:** the existing tests keep the default `0`.
- **Helper script:** `C:\temp\tokli-live-test\eval_smoke.cmd`, outside the repository, gets
  `--temperature default`.

## 6. Impact on architecture

None: one option in `tokli eval smoke`, passed to `request_body`.

## 7. Compatibility and migration

- **Record:** no change to the record format. The report gains one provenance row
  ("Temperature").
- **Config:** no change to config keys, persisted schema or fingerprints.
