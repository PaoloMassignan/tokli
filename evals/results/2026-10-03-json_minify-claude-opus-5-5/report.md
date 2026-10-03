# Smoke evaluation: json_minify on claude-opus-5-5

**Verdict: no_measurable_damage.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.0.dev0 |
| Compressor | json_minify v1 |
| Model | claude-opus-5-5 |
| Date | 2026-10-03 |
| Version of the case set | 2026-10-03.1 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | 27c7973acbca25cb28f1c95b42aa68c929fa1b4044ac8288d6e38a3f83023332 |
| config_hash candidate | efa4cfa4193bbd36389353c82da177531d1d8095177ef86921eacb1672d98f9b |
| Provider calls | 264 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| json_fact_lookup | reads_minified_json | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| json_verbatim_quote | not_quoted_verbatim | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |

## Errors

| Count | Type | Provider message |
|---|---|---|
| 2 | empty_answer |  |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 297,561 | 217,437 |
| forwarded input tokens, estimate (local) | 205,533 | 127,686 |
| compressor time (ms, total) | 0.0 | 10.0 |

Estimated saving: 77,847 tokens (37.9 % of the baseline estimate); exact difference from provider usage: 80,124 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
