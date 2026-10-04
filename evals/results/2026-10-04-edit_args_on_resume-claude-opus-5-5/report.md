# Smoke evaluation: edit_args_on_resume on claude-opus-5-5

**Verdict: damage_detected.** The smoke tier detects only gross damage (SPEC 012, QE-015).

## Provenance

| Field | Value |
|---|---|
| Tokli version | 0.1.0.dev0 |
| Compressor | edit_args_on_resume v1 |
| Model | claude-opus-5-5 |
| Date | 2026-10-04 |
| Version of the case set | 2026-10-04.2 |
| Repetitions | 3 |
| Temperature | model default |
| config_hash baseline | d1aacf2c260cd1d4e8ec681c752a893614e0d340ae31a7e5fc28d406e4974a61 |
| config_hash candidate | 46a861391a119bc7f3bb6cb6a88f9fc93e4481899e556c0a1c28721d1b875c0b |
| Provider calls | 132 |

## Results per assumption

| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | errors candidate | not exercised | incomplete | verdict |
|---|---|---|---|---|---|---|---|---|---|
| reread_after_pruned_edit | edit_content_not_needed | 20 | 4 | 0 | 2 | 6 | 0 | 0 | damage_detected |

## Errors

| Count | Type | Provider message |
|---|---|---|
| 23 | refusal |  |

## Tokens and time

| | baseline | candidate |
|---|---|---|
| forwarded input tokens, exact (provider usage) | 74,079 | 58,701 |
| forwarded input tokens, estimate (local) | 39,516 | 32,595 |
| compressor time (ms, total) | 0.0 | 0.1 |

Estimated saving: 6,921 tokens (17.5 % of the baseline estimate); exact difference from provider usage: 15,378 tokens.

A case passes in an arm when most of its repetitions pass. The verdict is `no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored case than the baseline, over at least 20 completed cases.
