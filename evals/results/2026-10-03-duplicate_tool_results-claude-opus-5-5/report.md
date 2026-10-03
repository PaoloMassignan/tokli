# Smoke evaluation: duplicate_tool_results on claude-opus-5-5

**Verdict: no_measurable_damage.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.0.dev0 |
| Compressor | duplicate_tool_results v1 |
| Model | claude-opus-5-5 |
| Date | 2026-10-03 |
| Version of the case set | 2026-10-03.1 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | 6e03de33e312f9a8d4117e499ec8351e1aa6d9593a7ea608c3a689ffaa547c25 |
| config_hash candidate | ff17834c668cf06128c5b569b64195f0fd3ad139c5e3ce3ad007aaba5603fc25 |
| Provider calls | 264 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| reference_fact_lookup | resolves_result_reference | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| reference_verbatim_quote | quotes_from_reference_target | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 231,198 | 179,514 |
| forwarded input tokens, estimate (local) | 155,940 | 116,448 |
| compressor time (ms, total) | 0.0 | 1.6 |

Estimated saving: 39,492 tokens (25.3 % of the baseline estimate); exact difference from provider usage: 51,684 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
