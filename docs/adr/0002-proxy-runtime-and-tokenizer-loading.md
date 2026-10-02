# ADR 0002 — Proxy runtime dependencies and tokenizer loading

Status: accepted (S1, 2026-09-30) · Related: ADR 0001, TOKLI_ARCHITECTURE.md §9, `slices/S1/SPEC_REVIEW.md` §6

## Context

S1 turns Tokli into a streaming HTTP proxy that counts tokens. That needs an ASGI server, an HTTP
client with streamed responses, TLS roots and a tokenizer. These are persistent third-party
dependencies (`CLAUDE.md §6`).

## Decision

| Concern | Choice | Why |
|---|---|---|
| ASGI framework | `starlette` | small; `StreamingResponse` cancels the relay when the client disconnects (PX-009) |
| Server | `uvicorn` | standard; accepts a pre-bound socket, so Tokli controls bind errors (PT-008) and the exclusive-bind option on Windows |
| HTTP client | `httpx` (async, `send(stream=True)`, `aiter_raw`) | streamed relay of raw bytes, so content encodings pass through; the read timeout applies between chunks (UP-009) |
| TLS roots | `certifi` (explicit dependency) | the same trust store on every OS, instead of each machine's system store (PT-001); a configured `tls.ca_bundle` replaces it (UP-008) |
| Tokenizer | `tiktoken` | exact tiktoken counts |
| Property tests (dev) | `hypothesis` | SPEC 009/010 `prop_*` tests |

**Tokenizer loading.** tiktoken's own loader downloads encodings and caches them in the system
temp directory. That is network access at run time and machine state outside the data dir (MD-02,
TM-007). Tokli instead:

1. reads the file that `tokli setup tokenizers` verified (pinned SHA-256, TM-010);
2. parses the ranks itself (one `base64 rank` pair per line);
3. builds `tiktoken.Encoding` with the split pattern and special tokens **pinned in
   `tokli.tokens.catalog`** (copied from tiktoken 0.14.0, MIT licence, attribution in the module
   docstring).

`test_token_counts_match_reference_values` and `test_token_counts_stable_fixture` compare Tokli's
counts with values produced by tiktoken's own `get_encoding` (committed golden files), for both
tokenizers.

## Consequences

- Runtime dependencies are now `pydantic`, `PyYAML`, `starlette`, `uvicorn`, `httpx`, `certifi`
  and `tiktoken`.
- A tiktoken release that changes an encoding would not affect Tokli until the pinned pattern or
  hash is updated deliberately, and the golden tests would flag the difference.
- `trust_env=False` on the HTTP client: proxies and CA settings are never taken silently from
  environment variables (MD-05, PT-002).
