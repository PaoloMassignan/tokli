# Smoke evaluation: reread_by_reference on claude-opus-5-5

**Verdict: no_measurable_damage.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.1 |
| Compressor | reread_by_reference v2 |
| Model | claude-opus-5-5 |
| Date | 2026-10-09 |
| Version of the case set | 2026-10-03.1, 2026-10-09.1 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | e1165f04437327ed12761b64b550c1360736f55a81a95603a8124d19aac7db68 |
| config_hash candidate | 1def1316b4266b86109b3148b703dacbf7b16d03097ac05f0010f48a8dbd70e2 |
| Provider calls | 396 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| reference_verbatim_quote | quotes_from_reference_target | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| reread_edit_anchor | quotes_from_reference_target | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |
| reread_fact_lookup | reads_partial_reference | 22 | 0 | 0 | 0 | 0 | 0 | 0 | no_measurable_damage |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 987,855 | 594,975 |
| forwarded input tokens, estimate (local) | 665,985 | 394,782 |
| compressor time (ms, total) | 0.0 | 43.4 |

Estimated saving: 271,203 tokens (40.7 % of the baseline estimate); exact difference from provider usage: 392,880 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
