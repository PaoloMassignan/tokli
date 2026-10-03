# Anthropic response fixtures (usage parsing)

Synthetic responses in the event and body shapes documented for the Anthropic Messages API. They
contain no real content: the only text is the canary `TOKLI-CANARY-RESPONSE`.

| File | Shape | Expected usage |
|---|---|---|
| `stream_basic.sse` | `message_start` with the full usage, `message_delta` with `output_tokens` only | input 25, cache_read 30,000, cache_write 5m 1,000 / 1h 200, output 15; `provider` |
| `stream_cumulative_delta.sse` | `message_delta` repeats the input fields (cumulative) | the last non-null value per field: input 40, output 22; `provider` |
| `stream_cumulative_delta_without_split.sse` | the shape observed in E4 (2026-10-03): the delta repeats input and cache totals, adds `iterations` and `output_tokens_details`, and has no `cache_creation` split | the 5m/1h split from `message_start` is kept: 1,000 / 200; output 42 |
| `stream_error_event.sse` | ends with an `error` event, no `message_delta` | input categories from `message_start`, output 1; `provider_partial` |
| `non_stream.json` | JSON body with the 5m/1h split | input 12, cache_read 4,000, 5m 0 / 1h 500, output 7 |
| `non_stream_without_cache_split.json` | no `cache_creation` object | `cache_creation_input_tokens` counts as 5m (300), 1h 0 |

Experiment E4 (S2, 2026-10-03) confirmed the event sequence and that `message_delta` repeats the
input fields cumulatively, without the 5m/1h split (SPEC 003, Q3). The values in these files are
synthetic; only the shapes come from E4.
