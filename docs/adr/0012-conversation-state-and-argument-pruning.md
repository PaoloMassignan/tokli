# ADR 0012 — Conversation state and pruning of tool-call arguments at resume

Status: accepted (S8c, 2026-10-04; approved at S8c Gate 1) · Related: SPEC 001 CM-009, SPEC 003, SPEC 009
CC-006, SPEC 019 PR-005, PR-020…PR-026, ADR 0010 (request-scope compressors), TOKLI_EVIDENCE §2
(E5b-lite)

## Context

Until S8a every compressor is a function of the request alone (CC-006), and tool-call arguments
are opaque (CM-009, PR-005).

The S8a measurements on real Claude Code sessions changed the picture:
- most cost is the provider cache;
- three quarters of the cache writes follow a pause of more than an hour, when the whole context
  is written again;
- pruning old `Write`/`Edit` arguments only at those moments, and keeping the pruning
  afterwards, was estimated at about 6 % of total cost.

To do that, Tokli must know three things that the request alone does not tell:
- that a request continues a conversation;
- when that conversation's previous request was;
- which replacements it decided at the last resume.

It must also be able to change argument strings of selected tool calls.

## Decision

- **Conversation key:** SHA-256 over the request's `system` value and its first message, in
  canonical JSON. Two requests with the same key belong to the same conversation. No header is
  needed, and nothing is stored but the hash.
- **Conversation store** (`tokli.app`, in memory):
  - it maps a key to the wall-clock time of the conversation's last request and the set of
    tool-call ids pruned at its last resume;
  - it is bounded by `pruning.conversation_states` (LRU) and never written to disk;
  - wall-clock time is used rather than a monotonic clock, so a sleeping machine still counts
    the pause.
- **Resume:** a request whose conversation was last seen more than `pruning.resume_after_s` ago,
  or whose conversation is unknown (product question P5), is a resume. At a resume the pruner
  chooses the calls to prune. At every other request it re-applies exactly the stored set, so
  the forwarded prefix stays byte-identical between resumes.
- **The pruner gets the state through the engine,** as a read-only view (time since the last
  request, the stored set), like the tool records of ADR 0010. The engine writes the new set back
  after the request is transformed. Compressors stay pure functions of their inputs.
- **Argument segments:**
  - The adapter exposes, for the tools and fields in `pruning.resume_edit_fields`, each argument
    string as a `TOOL_CALL_ARGS` segment, with its JSON Pointer into `tool_use.input`.
  - These segments are mutable only for request-scope compressors that declare `TOOL_CALL_ARGS`;
    segment compressors never see them.
  - Render patches the string in place: keys, `file_path`, ids and order are unchanged (CM-002,
    CM-004).

## Alternatives considered

- **A session header.** Rejected: not every client sends one, and its value would have to be
  stored.
- **Persisting the state on disk.** Not now: it adds a file format and its migration. After a
  restart, P5 decides what happens.
- **Pruning at a fixed age, on every request.** Rejected: every new item crossing the age line
  would rewrite the cached prefix, which costs more than it saves (H05, E5b-lite).
- **Asking the provider whether the cache is warm.** There is no such API. Rewrites are seen only
  in the response's usage, after the fact.

## Consequences

- **Tests:** the conversation key, the resume rule with an injected clock, byte-identical
  re-application between resumes, LRU bounds, argument round-trip and structure preservation for
  `Write`/`Edit`/`MultiEdit`.
- **A wrong resume guess costs one cache write:** a prune while the cache is still warm. The
  dashboard shows `cache_creation_input_tokens` per request, so this is visible.
- **Portability:** none specific; the wall clock is the only new input.
- **Migration:** none. New config keys only; the stub text is part of the compressor version.
