# SPEC 006 — Upstream endpoints and authentication

Status: Draft · Slice: S1 (passthrough, Anthropic), S5 (inject, both) · Related: ARCH §2, §6
Approved for S1 (2026-09-30): UP-001, UP-002, UP-005, UP-006, UP-008, UP-009, UP-010, and live tests E1a (API key) and E1b (Pro/Max OAuth). Inject mode in S5.

## Purpose
Keep provider endpoints and credentials explicit, separate from compression, and impossible to
confuse across providers.

## Rationale
- Credentials come only from explicitly configured sources. Implicit discovery (inherited environment variables, many search locations) is a portability and support burden.
- A client's own provider key works in passthrough.
- No credential material, not even a prefix, reaches a log.
- Key files written by Windows tools may carry a BOM or be UTF-16 encoded.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 006 rows).

## Auth support matrix (v1 target; status after the named experiment)

| Client / credential | Mode | Status |
|---|---|---|
| Anthropic API key (`x-api-key`) from client | passthrough | SUPPORTED (S1); live test E1a on 2026-10-02 |
| Anthropic API key held by Tokli | inject | SUPPORTED (S5) |
| Claude Pro/Max OAuth (`Authorization: Bearer`, `anthropic-beta` OAuth flag) from Claude Code | passthrough | **SUPPORTED (S1)**: live test E1b on 2026-10-02, 16 requests through Tokli with a Pro/Max login, all relayed with `credential_kind = oauth` (`slices/S1/COMPLETION_REPORT.md`). Nothing in auth is transformed. |
| OpenAI API key (`Authorization: Bearer sk-…`) from client | passthrough | SUPPORTED (S5) |
| OpenAI API key held by Tokli | inject | SUPPORTED (S5). Required by the product brief. |
| Codex with ChatGPT-subscription login | — | NOT SUPPORTED (E6) |

## Configuration

```yaml
upstreams:
  anthropic: {base_url: "https://api.anthropic.com", connect_timeout_s: 10, read_timeout_s: 600}
  openai:    {base_url: "https://api.openai.com",    connect_timeout_s: 10, read_timeout_s: 600}
auth:
  anthropic: {mode: passthrough}                         # or: {mode: inject, key_env: MY_ANTHROPIC_KEY}
  openai:    {mode: inject, key_file: "C:/secrets/openai.key"}
tls:
  ca_bundle: null        # explicit path only; default = certifi bundle
```

## Requirements

| ID | EARS requirement |
|---|---|
| UP-001 | THE SYSTEM SHALL take each provider's upstream base URL from configuration (default: official endpoint) and SHALL report it in diagnostics. |
| UP-002 | WHILE a provider's auth mode is `passthrough`, THE SYSTEM SHALL forward the client's credential headers unchanged and SHALL NOT store them beyond the lifetime of the request. |
| UP-003 | WHILE a provider's auth mode is `inject`, THE SYSTEM SHALL remove client credential headers (`authorization`, `x-api-key`) and set the provider's header (`x-api-key` for Anthropic, `Authorization: Bearer` for OpenAI) from exactly one configured source (`key_env` or `key_file`). |
| UP-004 | IF inject mode is configured AND the configured source is missing, empty or unreadable, THEN THE SYSTEM SHALL answer 503 with `tokli_missing_credential` naming the configured source (not its value) and SHALL NOT forward the request. |
| UP-005 | THE SYSTEM SHALL NOT use one provider's credential for another provider, and SHALL NOT read any credential source that is not named in configuration. |
| UP-006 | THE SYSTEM SHALL NOT write credential values to logs, telemetry, traces, diagnostics or API responses. It MAY record `credential_kind ∈ {api_key, oauth, none, unknown}` derived from header name and prefix only. |
| UP-007 | WHEN reading a `key_file`, THE SYSTEM SHALL strip a UTF-8 BOM, surrounding whitespace and zero-width characters, and SHALL reject values that are not printable ASCII with a diagnostic naming the file. |
| UP-008 | THE SYSTEM SHALL verify upstream TLS certificates, using a custom CA bundle only when `tls.ca_bundle` is configured. |
| UP-009 | THE SYSTEM SHALL apply configured connect/read timeouts. The read timeout applies between stream chunks, not to the whole stream. |
| UP-010 | THE auth component SHALL operate on headers only, and SHALL be applied after rendering, so the forwarded body is independent of the auth mode. |

## Acceptance criteria
- AC-UP-1 (UP-002): the fake upstream receives exactly the client's `x-api-key` / `authorization` / `anthropic-beta` / `openai-organization` headers in passthrough.
- AC-UP-2 (UP-003, UP-005): in inject mode the fake upstream sees only the injected key, and an OpenAI-bound request never carries the Anthropic key.
- AC-UP-3 (UP-004): a missing env var → 503 with code; the upstream received nothing.
- AC-UP-4 (UP-006): canary keys never appear in logs, SQLite or API output.
- AC-UP-5 (UP-007): BOM and UTF-16 key files → accepted and rejected respectively, with the diagnostics named.
- AC-UP-6 (UP-010): the same request in both modes → identical upstream body bytes.
- AC-UP-7 (E1): after the experiment, the matrix row for OAuth is updated with evidence.

## Test scenarios
`test_passthrough_forwards_client_credentials` · `test_inject_replaces_client_credentials` ·
`test_inject_uses_only_configured_source` · `test_inherited_provider_env_is_ignored_unless_configured` ·
`test_missing_inject_credential_returns_503` · `test_no_cross_provider_credentials` ·
`test_logs_never_contain_credentials` · `test_key_file_with_bom_is_accepted` · `test_utf16_key_file_reported` ·
`test_body_independent_of_auth_mode` · `test_tls_verification_default_on` · `test_read_timeout_between_chunks` · `test_credential_kind_classification`

## Open questions
- ~~Q8~~ Resolved 2026-09-28: the product owner is comfortable with OAuth passthrough. It becomes SUPPORTED once E1 passes.
