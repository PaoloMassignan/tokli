# TOKLI — Telemetry, Token Accounting and Cost Model

Normative requirements: `specs/008-token-measurement`, `specs/013-telemetry-and-cost`.
This document explains the model and why it is shaped this way.

## 1. Three kinds of token number, never mixed silently

| Method | Where it comes from | Used for | Label shown |
|---|---|---|---|
| `exact` | Provider `usage` in the response to **the forwarded request** | Forwarded input/output/cache tokens | "exact (provider)" |
| `estimate` | Local tokenizer (`tiktoken`, id recorded) on segment text | Per-segment before/after, gates, per-compressor attribution | "estimate (o200k)" |
| `calibrated` | `estimate × k`, where `k = exact_forwarded_input_total / estimate_forwarded_input_total` for the same request | Original request size and total saving in provider units | "calibrated estimate" |

Rules:

- The **original** request is never sent, so its size is always an estimate or a calibrated
  estimate. It is never "exact".
- `k` is computed per request and stored. It is **not** applied to per-compressor figures in
  storage. The query layer applies it. That keeps attribution additive and reproducible.
- When provider usage is unavailable (OpenAI Chat stream without `include_usage`, upstream error,
  parser failure), `k` is null and figures stay `estimate`.
- Tokenizer choice is config (`tokens.model_map`: glob → tokenizer id). The default maps
  `gpt-*`, `o*` → `o200k_base` and `claude-*` → `o200k_base` (a proxy tokenizer). The label always
  says "proxy tokenizer" for Claude. E3 measures the proxy error.

`estimate_forwarded_input_total` needs a local estimate of the whole forwarded request, not only
the mutable segments. Tokli estimates it as the sum of all segment texts plus
`tokenizer(json.dumps(non-text structure))`, without binary payloads (base64 image and document
data, thinking signatures), which the provider does not count as text (TM-004). It is computed
off the latency path, while the upstream is answering. It is crude. That is acceptable because it is only
used to compute a ratio, and `k` is stored so its distribution can be inspected. It is a
diagnostic signal of tokenizer drift in its own right.

## 2. Records

One `RequestRecord` per proxied API request, plus one `CompressorStats` row per
(request × compressor that was considered at least once). Per-segment detail is **not**
persisted by default. It is available in the in-memory trace ring buffer and at
`telemetry.detail: segment`.

### RequestRecord (persisted)

| Field | Type | Notes |
|---|---|---|
| `request_id` | text (ULID) | also in response header `x-tokli-request-id` |
| `ts_start`, `ts_end` | UTC ISO-8601 | |
| `provider`, `protocol`, `endpoint` | text | from route |
| `model` | text \| null | from request body |
| `stream` | bool | |
| `auth_mode` | `passthrough` \| `inject` | never any credential material |
| `credential_kind` | `api_key` \| `oauth` \| `none` \| `unknown` | prefix classification only |
| `policy` | `LOSSLESS_ONLY` \| `LOSSY_ALLOWED` | effective at request start |
| `config_hash` | text | hash of the effective compression-relevant config |
| `outcome` | `compressed` \| `passthrough` \| `verbatim_route` \| `error` | |
| `passthrough_reason` | text \| null | e.g. `no_applicable_compressor`, `parse_error`, `content_encoding`, `too_large`, `policy_off` |
| `segments_total`, `segments_mutable`, `segments_changed` | int | |
| `tokenizer_id` | text | |
| `est_original_tokens`, `est_forwarded_tokens` | int | mutable-segment scope, **estimate** |
| `est_request_tokens_original`, `est_request_tokens_forwarded` | int | whole-request estimate (for `k`) |
| `usage_source` | `provider` \| `provider_partial` \| `unavailable` | partial: stream cut short after `message_start` (AN-010) |
| `usage_input`, `usage_cache_read`, `usage_cache_write_5m`, `usage_cache_write_1h`, `usage_output`, `usage_reasoning` | int \| null | provider categories mapped per §4 |
| `calibration_k` | real \| null | |
| `status_code` | int | upstream status relayed |
| `ms_parse`, `ms_pipeline`, `ms_render`, `ms_upstream_ttfb`, `ms_upstream_total`, `ms_tokli_overhead` | real | overhead = total − upstream wall time |
| `history_rewritten` | bool | a non-prefix-stable compressor changed an already-sent segment (PR-009) |
| `reference_stubs` | int | reference stubs forwarded in this request (TC-014) |
| `error_code` | text \| null | Tokli error taxonomy (OB spec) |
| `header_names` | JSON list \| null | client request header names, lower-cased and sorted, never values (OB-012; schema v2) |

### CompressorStats (persisted, per request × compressor)

| Field | Notes |
|---|---|
| `request_id`, `compressor_id`, `compressor_version`, `kind` | |
| `considered` | segments where the compressor passed the policy + enabled + available filters |
| `applicable` | of those, where `applicable()` returned true |
| `accepted` | transformations kept |
| `rejected_no_gain`, `rejected_invariant`, `failed`, `skipped_budget` | counters |
| `tokens_in` | Σ estimate of input text over **applicable** invocations |
| `tokens_out` | Σ estimate of output text over applicable invocations (= input when rejected) |
| `marginal_saved` | `tokens_in − tokens_out` (≥ 0 by construction) |
| `ms_total` | Σ wall time spent in `applicable()` + `compress()` + the engine's check for this compressor |
| `skip_reasons` | JSON histogram, e.g. `{"too_small": 41, "verbatim_tool": 3, "not_json": 12}` |

**Attribution invariant (tested):** for every request,
`Σ_compressors marginal_saved == est_original_tokens − est_forwarded_tokens`. It holds because
the engine processes a chain sequentially and each step's input is the previous step's accepted
output.

**Order dependence (documented, not hidden):** marginal attribution depends on chain order.
Compressor B's figure is "what B saved *after* A". The dashboard says so. The eval harness also
reports *isolated* savings (each compressor alone on the same corpus) so users can compare.

## 3. Aggregates the dashboard and API provide

Per time range × {provider, model, compressor, compressor kind}:

- requests, compressed-request share, pass-through share by reason;
- original tokens (calibrated when possible), forwarded tokens (exact when possible), saved tokens, saving %;
- per compressor: invocations (`considered`), applicable, accepted, tokens processed (`tokens_in`),
  total marginal saving, **average saving % per accepted invocation**, **marginal share of total
  saving**, total and average latency, **zero-benefit rate** = (applicable − accepted) / applicable,
  failure rate = failed / applicable, **tokens saved per ms** (efficiency);
- estimated cost: forwarded, original, saved, each with method and bounds (§5);
- **Tokli overhead distribution** (n, p50, p95, p99, max) per request-size bucket (< 10k, 10k–50k,
  50k–200k, > 200k estimated input tokens), per policy and per `config_hash`. The Vision target is
  shown as a labelled reference value, never as pass/fail (TC-013, TOKLI_TEST_STRATEGY §8).

"Which compressors cost latency but save nothing?" is answered by sorting on tokens-saved-per-ms
and on the zero-benefit rate. The UI flags compressors with ≥ 90 % zero-benefit and ≥ 1 ms
average latency over ≥ 100 applicable invocations.

## 4. Mapping provider usage to categories

| Tokli category | Anthropic Messages | OpenAI Chat | OpenAI Responses |
|---|---|---|---|
| `input` (uncached) | `usage.input_tokens` | `prompt_tokens − prompt_tokens_details.cached_tokens` | `input_tokens − input_tokens_details.cached_tokens` |
| `cache_read` | `cache_read_input_tokens` | `prompt_tokens_details.cached_tokens` | `input_tokens_details.cached_tokens` |
| `cache_write_5m` / `_1h` | `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` (fallback: `cache_creation_input_tokens` → 5m) | — | — |
| `output` | `output_tokens` | `completion_tokens` | `output_tokens` |
| `reasoning` (subset of output) | — | `completion_tokens_details.reasoning_tokens` | `output_tokens_details.reasoning_tokens` |

Streaming locations (Anthropic `message_start` + `message_delta`; OpenAI Chat final chunk only
when the client set `stream_options.include_usage`; Responses `response.completed`) are
**REQUIRES EXPERIMENT E4**. Tokli must never add `stream_options` to a client request (that would
change the stream the client receives).

## 5. Cost model

### Price book

A versioned YAML file shipped with Tokli, overridable by the user:

```yaml
version: 2026-09-28.1
currency: USD
source_note: "Copied from provider pricing pages on 2026-09-28; verify before relying on it."
models:
  - match: "claude-sonnet-4*"          # glob on the request's model string
    provider: anthropic
    effective_from: 2026-01-01
    per_mtok: {input: 3.00, cache_write_5m: 3.75, cache_write_1h: 6.00, cache_read: 0.30, output: 15.00}
  - match: "gpt-5*"
    provider: openai
    effective_from: 2026-01-01
    per_mtok: {input: 1.25, cache_read: 0.125, output: 10.00}
```

The prices above are **placeholders for illustration**. Real values are filled in, and dated, when
slice S6 is implemented. Tokli never ships a price without a date and source note. A model with no
match has pricing `unavailable`.

### What Tokli claims

Tokli only reduces **input-side** tokens. It never claims output savings, even though shorter
context can change output length. That effect is not attributable and is excluded.

For each request with known pricing and known usage:

```text
forwarded_cost  = Σ_c usage_c × price_c                               (method: exact-usage × price book)
saved_tokens    = calibrated (or estimated) input-side saving
mix_c           = usage_c / Σ input-side usage_c      for c ∈ {input, cache_read, cache_write_*}
saved_cost_est  = saved_tokens × Σ_c mix_c × price_c                  (method: "proportional")
saved_cost_low  = saved_tokens × min_c∈present price_c                (usually cache_read)
saved_cost_high = saved_tokens × max_c∈present price_c                (usually cache_write)
original_cost   = forwarded_cost + saved_cost_est
```

Why proportional: Tokli does not know which of the saved tokens would have fallen in the cached
prefix. The forwarded request's own mix is the best available evidence. The range makes the
uncertainty visible. With an agent session that is mostly cache reads, a 10,000-token saving can be
worth 10× less than a naive "× input price" figure. Flat-price dashboards always use the naive figure (H22).

When usage is unavailable: `saved_cost_est = saved_tokens × price_input`, labelled
"assumes uncached input", with `saved_cost_low = saved_tokens × price_cache_read` when that price
is known.

When pricing is unavailable: every cost field is `null` with `reason: "no_price_for_model"`.
The UI shows "—" with a tooltip. Tokens are still shown.

### Cache-invalidation cost (known, not modelled in v1)

Turning Tokli on, off, or changing compressor config mid-session changes the bytes of already-sent
history once. The next request then writes a new cache prefix (Anthropic 1.25× price). v1 does not
estimate this. It records `config_hash` so the event is visible, and E2 quantifies it.

## 6. Retention and privacy

- Default retention: 30 days for `RequestRecord`/`CompressorStats`, configurable (0 = keep forever).
  Pruned at startup and every 24 h.
- No prompt text, no tool names (only a `verbatim_tool` skip counter), no file paths, no model
  outputs are stored. Tool names can be recorded in aggregate only when
  `telemetry.record_tool_names: true`, because tool names may reveal internal MCP servers.
- Debug-content capture is covered in `TOKLI_OBSERVABILITY.md §5` and is off by default.
