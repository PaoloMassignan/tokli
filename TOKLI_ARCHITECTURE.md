# TOKLI — Architecture

Status: proposal for review. Nothing here is implemented.

## 1. Shape in one picture

```text
          client (Claude Code / Codex / SDK)
                     │  HTTP, base URL = http://127.0.0.1:<port>/<provider-prefix>
                     ▼
┌──────────────────────── tokli.http (thin) ────────────────────────┐
│ route by prefix → RequestContext(request_id, clock, config snap)  │
│ unknown path / non-JSON / encoded body ─────────────► verbatim ───┼──┐
└──────────────┬────────────────────────────────────────────────────┘  │
               │ raw bytes + headers                                    │
               ▼                                                        │
      ProtocolAdapter.parse(raw) ──► CanonicalRequest                   │
      (anthropic_messages | openai_chat | openai_responses)             │
               │                                                        │
               ▼                                                        │
      Pipeline (ordered stages, from config)                            │
        1. analyzers   – mark protected spans, compute cheap features   │
        2. transformers – [future: redaction] → compression stage       │
               │  produces Patches + CompressionReport                  │
               ▼                                                        │
      ProtocolAdapter.render(original, patches) ──► bytes               │
      (no patches ⇒ original bytes, untouched)                          │
               │                                                        │
               ▼                                                        │
      Auth (passthrough | inject) → Upstream/Forwarder ◄────────────────┘
               │  relay status/headers/body; streams byte-for-byte
               │  tee → ProtocolAdapter.usage_parser (passive)
               ▼
      provider (api.anthropic.com / api.openai.com / configured)

 Cross-cutting, never called *by* compressors:
   tokli.tokens (counting) · tokli.telemetry (records → sinks) · tokli.pricing (query-time)
   tokli.observability (trace, decisions, structured log) · tokli.config

 Application layer (tokli.app): MetricsQuery · ConfigService · Diagnostics
   ▲ consumed by /tokli/api (JSON) ▲ consumed by the static dashboard and the CLI
```

## 2. Module map and responsibilities

Python ≥ 3.11 package `tokli` (import root `tokli`, **not** `src`). A generic `src` package name
collides with other projects (MD-19).

| Module | Responsibility | Owns | Must not know about |
|---|---|---|---|
| `tokli.domain` | Canonical model: `CanonicalRequest`, `Segment`, `SegmentKind`, `Span`, `Patch`, `Usage`, `TokenFigure(method)` | data types, invariants | HTTP, providers, compressors, storage |
| `tokli.protocols.<name>` | Map one wire protocol to and from the canonical model; parse usage from responses and streams | JSON shape knowledge of one protocol | other protocols, compression, auth, pricing |
| `tokli.upstream` | Provider endpoints (base URL, timeouts, TLS), HTTP forwarding, stream relay + tee | httpx client lifecycle | request content, compression |
| `tokli.auth` | Credential policy per provider: `passthrough` or `inject`; header rewriting; credential classification (api_key / oauth / unknown) **without retaining values** | credential sources | compression, telemetry storage |
| `tokli.pipeline` | Ordered stages over a `CanonicalRequest`; stage timing; failure isolation | stage contract | protocols, providers |
| `tokli.compression` | Compressor contract, registry, policy, planner/router, engine (chain, acceptance gate, invariants, attribution) | compression decisions | protocols, providers, HTTP, pricing, UI |
| `tokli.compressors.<id>` | One compressor each (+ decoder for LOSSLESS) | its algorithm | everything except `compression` contract and `domain` |
| `tokli.tokens` | `TokenCounter` interface; `tiktoken`-backed estimators; tokenizer data location | tokenizer identity | providers' pricing, compressors' logic |
| `tokli.telemetry` | Record types (`RequestRecord`, `CompressorRequestStats`), sinks (SQLite, JSONL log), retention | persistence schema | pricing, UI, compressor internals |
| `tokli.pricing` | Versioned price book; cost estimation from token categories at query time | prices | compression, HTTP |
| `tokli.observability` | Request context, stage spans, decision events, secret/content-safe logging | trace format | business rules |
| `tokli.config` | Load, merge (precedence), validate, expose effective config with per-key source; persist UI overrides | config schema | module internals |
| `tokli.app` | Use cases: `MetricsQuery`, `ConfigService`, `Diagnostics` (doctor, fingerprint) | application API | HTTP framework |
| `tokli.http` | ASGI app: proxy routes, `/tokli/api/*`, static UI, health | routing, request/response glue | compression internals |
| `tokli.cli` | `serve`, `doctor`, `config show` | argument parsing | — |
| `ui/` (static) | Dashboard (vanilla HTML/JS, no build step) | presentation | anything but `/tokli/api` |

## 3. The canonical model (summary; normative text in `specs/001`)

Design choice: **patch-based round-trip, not a universal message schema.**

```text
CanonicalRequest
  protocol: "anthropic_messages" | "openai_chat" | "openai_responses"
  provider: "anthropic" | "openai"           (from the route, not guessed)
  model: str | None
  stream: bool
  segments: list[Segment]                    (document order)
  tools: list[ToolRecord]                    (read-only: call_id, name, parsed args, result segment ids)
  original: parsed JSON (read-only) + original bytes

Segment
  id: str                                    (stable within the request: "s17")
  kind: SYSTEM | TOOL_DESCRIPTION | USER_TEXT | ASSISTANT_TEXT
        | TOOL_CALL_ARGS | TOOL_RESULT | OTHER_TEXT
  role: "system" | "user" | "assistant" | "tool" | None
  text: str                                  (the exact string value at `locator`)
  locator: JSON Pointer into original        (e.g. /messages/4/content/1/content/0/text)
  mutable: bool                              (protocol + config eligibility)
  attrs: {tool_name?, tool_call_id?, is_error?, cache_breakpoint_after?: bool, index: int}
  protected: list[Span]                      (filled by analyzers)

Patch  = (segment_id, new_text, produced_by: stage/compressor ids)
```

Why this is minimal and safe:

- Adapters expose **only string values** as segments. Everything else stays in `original` and is
  re-emitted untouched: images, `thinking` + signatures, encrypted reasoning, tool schemas,
  `cache_control`, unknown block types, unknown top-level fields. Forward compatibility is free.
- `render(original, [])` returns the **original bytes** (byte identity). `render(original, patches)`
  replaces exactly the patched string values and re-serialises once.
- Future redaction is a transformer producing patches on the same segments. Adapters do not change.

## 4. Pipeline and extension seams

The seams below exist because the variability already exists. Each one lists its first two
concrete implementations. They are **allowed boundaries**, not a build list. A seam becomes an
abstraction in code (a Protocol, registry or config switch) only in the slice where it is required,
or where two concrete implementations exist (`CLAUDE.md §5`). Until then the single
implementation is a concrete class inside its module. For example, `ProtocolAdapter` and
`CredentialPolicy` would get their interfaces in S5, when the second adapter and the inject mode arrive.

| Seam (interface) | Variability it absorbs | Implementations in v1 | Next known implementation |
|---|---|---|---|
| `ProtocolAdapter` | wire formats | anthropic_messages, openai_chat, openai_responses | gemini (future) |
| `UpstreamEndpoint` (data, not a class hierarchy) | provider hosts | anthropic, openai | azure-openai, bedrock (future) |
| `CredentialPolicy` | auth modes | passthrough, inject | — (two is enough) |
| `Stage` (analyzer or transformer) | pre-forward processing | reminder-span analyzer, content-feature analyzer, compression transformer | redaction transformer (future) |
| `Compressor` (scope `segment`) | text algorithms | json_minify, later search_group, dictionary, diff_context_trim, log_filter | … |
| `Compressor` (scope `request`, "pruner") | tool-history reduction | duplicate_tool_results (LOSSLESS, reference) | superseded_tool_results (SELECTIVE) |
| Tool semantics (config data + one analyzer) | client-specific tool meaning (Claude Code tools, Codex shell commands) | Claude Code defaults, Codex classifier | other clients via config |
| `TokenCounter` | tokenizers | tiktoken o200k, tiktoken cl100k | provider count endpoint (offline eval only) |
| `TelemetrySink` | consumers of records | SQLite store, structured log | OpenTelemetry exporter (future) |

Rejected seams (YAGNI): plugin discovery via entry points, dynamic loading from config paths,
generic "middleware" chains around HTTP, abstract repository layers over SQLite, event bus.

### Stage contract

```python
class Stage(Protocol):
    id: str                      # "analyze.reminders", "transform.compression"
    kind: Literal["analyzer", "transformer"]
    def run(self, req: CanonicalRequest, ctx: StageContext) -> StageResult: ...
# analyzers may add protected spans / features; transformers return patches.
# The pipeline applies patches between transformers so later stages see earlier output.
```

Ordering is explicit in config (`pipeline.stages`) with a validated default. In v1 validation
checks only that every stage is known and that analyzers precede transformers (PL-002). A future
`transform.redaction` must sit before `transform.compression`. The slice that adds it also adds a
`must_precede` declaration, so the rule is data on the stage, not special-casing in the core.

### Compressor contract (summary; normative in `specs/009`)

```python
@dataclass(frozen=True)
class CompressorSpec:
    id: str; name: str; version: str
    kind: Literal["LOSSLESS", "LOSSY", "SELECTIVE", "UNKNOWN"]
    equivalence: Literal["byte", "structural", "reference", "none"]  # LOSSLESS requires byte|structural|reference
    scope: Literal["segment", "request"]; prefix_stable: bool
    guarantees: tuple[str, ...]     # PROVEN, each backed by a named test
    assumptions: tuple[str, ...]    # ASSUMPTION ids, each covered by an evaluation case family
    stage: Literal["normalize", "structural", "domain", "semantic"]
    segment_kinds: frozenset[SegmentKind]
    cost_class: Literal["cheap", "moderate", "expensive"]
    terminal: bool                  # nothing runs after it on the same segment
    requires: tuple[str, ...]       # optional module names; missing ⇒ "unavailable"
    default_enabled: bool
    config_schema: type[BaseModel]

class Compressor(Protocol):
    spec: CompressorSpec
    def applicable(self, seg: SegmentView, features: Features) -> Applicability: ...
    def compress(self, text: str, seg: SegmentView) -> str | None: ...   # None = no change
    # LOSSLESS compressors additionally provide:
    def decode(self, text: str) -> str: ...
# Request-scope compressors (pruners) implement plan() and, for equivalence "reference",
# decode_request(). Normative contract: specs/009.
```

The engine owns everything cross-cutting: policy filtering, token counting before and after,
the acceptance gate, the protected-span check, reference integrity, timing, exception isolation and records. A
compressor is a pure function plus metadata. It cannot see other segments, the protocol,
the provider, prices or storage.

## 5. Dependency rules (enforced by an import-linter test)

> **Since S1 the enforced rules are those of ADR 0004** (`docs/adr/0004-module-dependency-rules-from-s1.md`,
> accepted 2026-10-02): `tokli.app.bootstrap` is the composition root, and the list below is kept
> as the original intent. Every forbidden edge below still holds.

```text
tokli.http        → tokli.app, tokli.pipeline, tokli.protocols, tokli.upstream, tokli.auth,
                    tokli.observability, tokli.config, tokli.domain
tokli.app         → tokli.telemetry, tokli.pricing, tokli.config, tokli.compression (registry
                    metadata only), tokli.tokens, tokli.domain
tokli.pipeline    → tokli.domain, tokli.observability
tokli.compression → tokli.domain, tokli.tokens, tokli.observability
tokli.compressors.* → tokli.compression (contract only), tokli.domain
tokli.protocols.* → tokli.domain
tokli.upstream    → tokli.domain, tokli.observability
tokli.auth        → tokli.domain
tokli.telemetry   → tokli.domain
tokli.pricing     → tokli.domain
tokli.tokens      → tokli.domain
tokli.domain      → (stdlib only)

FORBIDDEN (checked):
tokli.compression, tokli.compressors  ↛ tokli.protocols, tokli.upstream, tokli.auth, tokli.http,
                                        tokli.pricing, tokli.telemetry(storage), ui
tokli.protocols.X ↛ tokli.protocols.Y   (no adapter reuses another's code)
tokli.protocols   ↛ tokli.compression, tokli.auth, tokli.pricing
tokli.telemetry   ↛ tokli.pricing        (cost is computed at query time)
ui                ↛ anything but /tokli/api over HTTP
any module        ↛ module-level I/O (no tokenizer/model loading at import time)
```

Shared helpers used by more than one adapter (e.g. SSE line framing) live in
`tokli.protocols._sse`, which is protocol-neutral and imports nothing protocol-specific.

## 6. Request lifecycle and failure model

| Step | Normal | On error | Rationale |
|---|---|---|---|
| Route | prefix → provider + protocol | unknown path under a known prefix → verbatim relay to that provider; unknown prefix → 404 `tokli_unknown_route` with a hint | never guess a provider (H32) |
| Read body | bytes | `content-encoding` present / non-JSON / above `max_transform_bytes` → verbatim | never reject what the provider would accept |
| Parse | CanonicalRequest | parse error → verbatim + decision `passthrough(parse_error)` | fail open to pass-through |
| Pipeline | patches | stage exception → that stage's patches discarded, recorded; others continue | isolation |
| Compression | per segment chain | compressor exception/timeout/invariant breach → segment unchanged, recorded | isolation |
| Render | bytes | render error → **original bytes** forwarded, recorded | fail open |
| Auth | headers | inject mode with missing key → **503 `tokli_missing_credential`**, nothing forwarded | fail closed on credentials |
| Forward | relay | connect/timeout → 502 `tokli_upstream_unreachable` (JSON, `source: tokli`); upstream 4xx/5xx → relayed verbatim | the client must see the provider's own errors |
| Stream | relay chunks unmodified, tee to usage parser | parser error → usage `unavailable`, stream untouched; client disconnect → cancel upstream | streaming semantics preserved |
| Telemetry | async-safe write | sink failure → logged once per interval, request unaffected | telemetry never breaks traffic |

Fail-open here means **fail to pass-through**, the safe state for a compression proxy. It is unrelated to
fail-open or fail-closed policies for security filtering, which Tokli does not have.

## 7. Configuration ownership

A single `EffectiveConfig` snapshot is taken per request, so a config change never applies
halfway through a request. Precedence: `defaults < config file < environment < CLI flags <
UI overrides`. UI overrides may only change keys that no higher-priority layer (env/CLI) has
pinned. A pinned key is shown as locked in the UI with its source. Details: `specs/017`.

## 8. Strict architecture review — attempts to break it

| Attack | Finding | Resolution |
|---|---|---|
| Protocol logic leaking into compression | Compressors need to skip file-read outputs (verbatim hazard), and tool names are protocol-specific (`Read`, `shell_command`). | Adapters only *resolve* `tool_name` generically. The **exclusion list is config** (`compression.verbatim_tools`), matched by the engine. Compressors never see protocol names. |
| Provider logic leaking into compression | Tokenizer choice depends on provider/model. | `TokenCounter` is selected by the engine from config (`tokens.model_map`) and passed in. Compressors never count tokens. |
| Auth mixed with transformation | One handler that both transforms and authenticates (H38). | `tokli.auth` runs after rendering and only touches headers. Test: an auth-mode change yields an identical body. |
| Compression logic in HTTP handlers | Tempting "quick" slice-1 shortcuts. | The handler calls `pipeline.run()` only. Import-linter forbids `tokli.http → tokli.compressors`. |
| UI coupled to storage/compressors | UI toggles need compressor metadata. | UI reads `/tokli/api/compressors` (from registry `spec`) and writes `/tokli/api/config`. No UI code references compressor ids beyond the data it receives. |
| Pricing coupled to compressors | "cost saved per compressor" | Telemetry stores tokens per compressor. Pricing multiplies at query time. |
| Telemetry coupled to decisions | Using historical effectiveness to route | **Not in v1.** If added, it is a read-only `EffectivenessHints` analyzer input with its own spec, never a direct telemetry import in the router. |
| Global mutable state | tiktoken encoders, httpx clients, config | Created in `tokli.app.bootstrap()` and injected. Tokenizer encoders are cached per process after explicit load, never at import. Config is an immutable snapshot, swapped atomically on change. |
| Hidden machine state | CWD-relative config, `/run/secrets`, models folder | No CWD reads unless a path is given. Data dir resolved and printed. No optional model files in v1. |
| Strategy conditionals in core | Central `if strategy == …` chains (H13) | Registry iteration + spec metadata. Test: registry order + policy are the only inputs. |
| Singletons | `MetricsStore` global | One instance per app, passed by constructor. |
| Unclear config ownership | Environment honoured only without a config file (MD-05) | One loader, one precedence, source tracked per key. |
| Silent fallbacks | tree-sitter missing → identity | `requires` unmet ⇒ compressor state `unavailable(reason)`, visible in API/UI/doctor. |
| Multi-responsibility abstractions | One result type carrying routing, features and dictionaries | `Invocation` (engine record) is separate from the compressor's output (`str | None`). |
| Speculative frameworks | Stage ordering DSL, plugin loading | Explicit list + one ordering check (analyzers before transformers). No entry points. |
| Unnecessary DI | Interfaces for things with one implementation (forwarder, config loader) | Concrete classes. Seams only in §4. |
| Over-engineering | Three protocols in slice 1 | Slice 1 = one protocol, one compressor (see roadmap). |
| Prompt caching broken by transformation | Dedup-style rewriting of history | CC-006 determinism. Duplicate pruning stubs the *later* copy (prefix-stable). Superseding is declared `prefix_stable: false`, flagged per request (CC-018), gated by age and minimum-saving thresholds, and measured by E2-ext. |
| Pruning pulls client/protocol knowledge into compression | Which tool reads which file is client-specific (`Read`, `apply_patch`) | Adapters expose generic `ToolRecord`s. Tool meaning is config plus the `analyze.tool_resources` analyzer. Pruners see only `resource_key`/`action`. |
| A reference stub points at content that a later compressor removes | Duplicate stub names result *i*; a selective pruner later stubs *i*, so the reference dangles. | Reference integrity is a runtime engine invariant (CC-019): a non-equivalent change to a reference target is rejected. |
| "Lossless" read as "safe for the task" | Every transformation, even whitespace removal, relies on model behaviour. | Policy eligibility depends only on proven preservation. Default enablement depends on evaluated assumptions (CC-020, SPEC 012 smoke tier from S2.5). |
| An early latency number becomes an invariant | A fixed ms threshold in CI rejects a valuable compressor before any real measurement. | Four classes, kept apart (TOKLI_TEST_STRATEGY §8): correctness constraints (hard), regression limits (relative to a measured baseline), product targets (reported), router budgets (runtime config, visible skips). |
| Pruning breaks protocol pairing rules | Removing pairs and merging messages needs protocol atomicity rules (H07, H08) | v1 stubs result *content* only. Structure is untouched (PR-005). Structural removal waits for E10. |
| Streaming broken by response inspection | Parsing SSE on the hot path | Passive tee with bounded buffer. The client receives upstream bytes before parsing happens. |
| Tool-call ordering constraints | Moving text before `tool_result` (H07) | Patches replace string values in place. Block count and order are immutable (CM-002). |

Remaining tension, accepted: the `verbatim_tools` default list contains client-specific names
(`Read`, `Bash`, …). It is data in config and doctor shows it, but it is still a heuristic. E8
will replace guesswork with measurements.

## 9. Technology choices

| Choice | Reason | Alternative rejected |
|---|---|---|
| Python 3.11–3.13 | tiktoken and a mature streaming HTTP ecosystem; team familiarity. Algorithms are implemented from the specs (`CLAUDE.md §8`). | Rust/Go: rewrite cost with no evidence of a latency problem (per-segment compression in Python measured well under 10 ms; the high E5a latency came from processing whole conversations). Overhead is measured from S1, so this can be revisited with data. |
| Starlette + uvicorn (FastAPI optional) | Streaming responses, small surface | aiohttp: fine, less familiar |
| httpx | Proven streaming client with explicit stream lifecycle | — |
| SQLite (stdlib) | Local, zero-ops, WAL | DuckDB: extra native dependency |
| tiktoken with **explicitly provisioned** BPE files | Deterministic offline counts | Char/4 heuristic: not credible for attribution |
| Vanilla JS dashboard, no build step | A UI that needs a build step can silently disappear (H41) | React/Vite |
| pydantic v2 for config | Validation + JSON schema for the UI | — |
