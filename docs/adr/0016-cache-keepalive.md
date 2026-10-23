# ADR 0016 — Cache keepalive: timer-driven upstream requests and held requests

Status: accepted (S8l Gate 1, 2026-10-23) · Related: SPEC 020, SPEC 000 SC-008, SPEC 006 UP-002 (S8l SCR-001), SPEC 019 PR-021, ADR 0002, ADR 0011, ADR 0012

## Context

- **Until S8l, every upstream request answered a client request.** The keepalive (SPEC 020) sends
  requests on a timer, when no client is waiting.
- **A ping must repeat the last forwarded request** (E12): the body, which is prompt content, and
  the headers, which carry the client's credential in passthrough mode. Both must be held for up
  to the horizon (12 h by default).
- **The server already runs one event loop** (ADR 0002) and transforms off it (ADR 0011). The
  conversation store (ADR 0012) holds metadata only.

## Decision

- **A keepalive component in the app layer** (`tokli.app.keepalive`), built by the bootstrap and
  idle while `keepalive.enabled` is false. It is concrete: one class, one protocol (Anthropic
  Messages). No interface for other protocols until one needs it (CLAUDE.md §5).
- **Dependency direction:** the component uses `tokli.upstream` (the existing client and its
  timeouts), `tokli.protocols.anthropic_messages` (usage parser, conversation key) and the
  conversation store. The proxy handler (`tokli.http.proxy`) calls it after a client response
  completes, as it already uses the store. The edges `tokli.app → tokli.upstream` and
  `tokli.app → tokli.protocols` are allowed by the layers contract (ADR 0004) but are not in the
  original list of `TOKLI_ARCHITECTURE.md` §5; this ADR records them, and §5 gains a note.
- **Scheduling:** one asyncio task per kept conversation, sleeping on the wall clock until the
  next ping is due (KA-005), checking before it sends that the lifetime has not passed (KA-006).
  Tasks are cancelled when the conversation stops being kept, when the feature is turned off and
  at shutdown. No threads, no OS timers.
- **Held data:** per kept conversation, the forwarded body bytes, the forwarded headers, and four
  numbers (time sent, cache lifetime, prefix size, last successful ping). Memory only, in a dict
  bounded by `keepalive.max_conversations`. Dropped when the conversation stops being kept. The
  held objects are never passed to a logger, tracer, telemetry row or API view; the request
  record of a ping is built from usage and status only.
- **Bodies are held as forwarded bytes.** A ping replaces the `max_tokens` value in a parsed copy
  and serialises it again (compact JSON), so the JSON value equals the held one except
  `max_tokens` (KA-004). The cache key depends on the content, not on the JSON layout.

## Alternatives considered

- **Holding the client's original body and recompressing it at ping time:** the compressors'
  output may depend on the conversation state, which a ping must not change. Rejected.
- **A separate keepalive process:** it would need the credentials passed across a process
  boundary, and its own lifecycle on three OSes. Rejected.
- **Not holding passthrough credentials (inject mode only):** the developer uses passthrough with
  OAuth; the feature would not reach their traffic. Rejected by the human's answer to P3.
- **Retrying a failed ping:** a failure after a pause usually means an expired token or a busy
  provider; a retry costs money and the next client request repairs the cache anyway. Rejected
  (KA-008).

## Consequences

- **Tests:** a fake clock and the fake upstream drive the schedule in-process (SPEC 020 AC-KA-*);
  canary credentials and content are scanned in logs, traces, the database and the API.
- **Privacy:** prompt content and credentials live in Tokli's memory for up to the horizon, only
  while the feature is on (the default since S8l SCR-004). A memory dump of the Tokli process in that window
  would contain them, as it would contain an in-flight request today.
- **Portability:** a sleeping machine stops the timers; the wall-clock check turns a late ping
  into a stop (`expired`), never into a cold write. The same code on every OS.
- **Migration:** no data migration. The feature is on by default (S8l SCR-004), so a user who
  upgrades starts sending keepalive requests; the README and the user guide say so and how to
  turn it off.
