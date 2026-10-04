# Smoke evaluation: log_filter on claude-opus-5-5

**Verdict: no_measurable_damage.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.0.dev0 |
| Compressor | log_filter v1 |
| Model | claude-opus-5-5 |
| Date | 2026-10-04 |
| Version of the case set | 2026-10-03.1, 2026-10-03.2 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | 19c2dc7420e2c8ec10387adaf2fdc8958784c9af0f5c5139cda8fc9e75067b52 |
| config_hash candidate | 857037471f538188a41f145dac6167c18f343ef4cfc920a364b283ad89c0fee6 |
| Provider calls | 264 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| grep_verbatim_quote | not_quoted_verbatim | 0 | 0 | 0 | 0 | 0 | 22 | 0 | not_exercised |
| json_verbatim_quote | not_quoted_verbatim | 0 | 0 | 0 | 0 | 0 | 22 | 0 | not_exercised |
| log_fact_lookup | omitted_log_lines_not_needed | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| log_verbatim_quote | not_quoted_verbatim | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 456,636 | 90,771 |
| forwarded input tokens, estimate (local) | 325,251 | 43,836 |
| compressor time (ms, total) | 0.0 | 57.0 |

Estimated saving: 281,415 tokens (86.5 % of the baseline estimate); exact difference from provider usage: 365,865 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
