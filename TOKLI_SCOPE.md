# TOKLI — Scope (v1)

## In scope

| Area | v1 scope |
|---|---|
| Protocols | Anthropic Messages `POST /v1/messages`; OpenAI Chat Completions `POST /v1/chat/completions`; OpenAI Responses `POST /v1/responses`. Streaming and non-streaming for all three. |
| Other endpoints | Relayed verbatim (e.g. `/v1/models`, `/v1/messages/count_tokens`, `/v1/embeddings`). |
| Providers | Anthropic API; OpenAI API. Each upstream base URL is configurable, so compatible endpoints work, but only these two are tested. |
| Authentication | **Passthrough** (default): the client's own credentials are forwarded unchanged. **Inject**: Tokli adds a provider API key from an explicit source. OpenAI API-key auth is required and supported in both modes. |
| Compression | Registry of compressors with declared preservation class (LOSSLESS byte / structural / reference, SELECTIVE, LOSSY, UNKNOWN; SPEC 009) and declared behavioural assumptions. Global policy LOSSLESS ONLY (default) / LOSSY ALLOWED. Per-compressor enable/disable. Default enablement requires an evaluation record. |
| v1 compressors | `json_minify` (LOSSLESS, slice 1). Later slices: `search_group` (LOSSLESS, reimplemented), `dictionary` (LOSSLESS, off by default), `diff_context_trim` and `log_filter` (SELECTIVE, off by default). |
| Tool-history pruning | `duplicate_tool_results` (LOSSLESS by reference, prefix-stable, S4; on by default only if its smoke evaluation passes). `superseded_tool_results` (SELECTIVE, LOSSY ALLOWED only, S8). Both are content-level stubs with no structural removal. Tool semantics come from config. `edit_args_on_resume` (SELECTIVE, off by default, S8c): when a conversation resumes after its provider cache expired, the strings of old `Write`/`Edit` arguments become stubs. It keeps an in-memory conversation state (time of the last request, pruned call ids; ADR 0012), which is operational state, not a knowledge model or memory of the user's code. See `specs/019`. |
| Measurement | Local token estimates, provider-reported usage, calibrated savings, per-compressor marginal attribution, latency per stage. |
| Cost | Versioned price book; estimated saving with method and bounds; "unavailable" when pricing is unknown. |
| Observability | Request IDs, stage timings, decision records, structured logs, no content by default. |
| UI | Local dashboard: savings, per-compressor table, breakdowns, recent-request diagnostics (metadata), compressor toggles, diagnostics page. |
| Ops | `tokli serve`, `tokli doctor`, `tokli config show`. Windows, Linux, macOS; Python 3.11–3.14. |

## Explicit non-goals (v1)

Proprietary-code protection · PASS/REDACT/BLOCK · secret detection · semantic security filtering ·
a persistent knowledge model of the user's code · persistent knowledge or memory · claims, contradictions, freshness · RAG ·
autonomous model selection or model routing · documentation generation · **relevance-based**
pruning (needs a knowledge model; Tokli prunes only duplicates and superseded results) ·
structural removal of tool-call pairs, and stubbing of tool-call arguments other than by `edit_args_on_resume` (E10) ·
LLMLingua or any learned compressor · ML-based routing · retrieval tools that let the model fetch compressed-away content ·
injecting tools or cache breakpoints into client requests · response-side compression · multi-user
or remote deployment · any capability not listed under "In scope".

## Deliberately deferred (with a reason)

| Item | Why deferred | What would bring it back |
|---|---|---|
| Prose compression (deleting articles and connectives) | LOSSY; corrupts code (TOKLI_EVIDENCE H01) | A prose-only applicability gate plus non-inferiority on the eval suite |
| AST comment stripping | Verbatim-quoting hazard; line numbers change | E8 shows no increase in Edit failures |
| Block-level dedup of arbitrary text | Current design breaks prefix caching | Replaced by `duplicate_tool_results` (prefix-stable, tool results only). Generalising to other segment kinds needs E5b data. |
| Structural pair removal / argument stubbing | Protocol pairing rules; unknown provider validation of historical arguments | E10 |
| Compressing `system` / tool descriptions | Usually a cached prefix (worth ~10 % of base price), and these are instructions | E2 + E5 show material uncached volume |
| Compressing `/v1/messages/count_tokens` bodies | Affects the client's own context accounting | Product decision (see Open Questions) |
| ChatGPT-subscription Codex upstream | Not supported by existing code; feasibility unknown | E6 |
| Force/benchmark mode for a single compressor | Not needed for v1 decisions | The eval harness isolates a compressor through config (baseline vs candidate arm, QE-012), in `evals/`, not in the proxy |

## Guardrails that stay in force because they are cheap and protect users

These are not security features. They keep a local proxy from becoming a liability:

- bind to `127.0.0.1` by default;
- never log credentials;
- no prompt content in logs or telemetry unless debug-content mode is explicitly on;
- check `Origin`/`Host` on mutating admin endpoints.

## Future capabilities the architecture must not prevent

- A redaction or security stage inserted before compression (a pipeline transformer on the
  canonical model).
- More protocols (e.g. Gemini) and providers (Bedrock, Vertex, Azure OpenAI) as new adapters and
  upstream entries.
- Learned or LLM-based compressors as registry entries with `cost_class: expensive`.
- Alternative telemetry sinks (OpenTelemetry exporter) behind the `TelemetrySink` seam.
- A replacement UI consuming the same `/tokli/api`.
