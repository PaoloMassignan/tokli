# Smoke evaluation: search_group on claude-opus-5-5

**Verdict: no_measurable_damage.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.0.dev0 |
| Compressor | search_group v2 |
| Model | claude-opus-5-5 |
| Date | 2026-10-04 |
| Version of the case set | 2026-10-03.1, 2026-10-03.2 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | 19c2dc7420e2c8ec10387adaf2fdc8958784c9af0f5c5139cda8fc9e75067b52 |
| config_hash candidate | 88734a0e5539d1c48cdb5250aafef3dd06e2cbd017bc5b88b823398f252851ae |
| Provider calls | 264 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| grep_fact_lookup | reads_grouped_search | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| grep_verbatim_quote | not_quoted_verbatim | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| json_verbatim_quote | not_quoted_verbatim | 0 | 0 | 0 | 0 | 0 | 22 | 0 | not_exercised |
| log_verbatim_quote | not_quoted_verbatim | 0 | 0 | 0 | 0 | 0 | 22 | 0 | not_exercised |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 122,343 | 109,710 |
| forwarded input tokens, estimate (local) | 64,620 | 59,412 |
| compressor time (ms, total) | 0.0 | 2.5 |

Estimated saving: 5,208 tokens (8.1 % of the baseline estimate); exact difference from provider usage: 12,633 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
