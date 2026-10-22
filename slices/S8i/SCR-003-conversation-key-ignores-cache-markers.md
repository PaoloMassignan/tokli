# S8i SCR-003 — The conversation key ignores cache markers

Status: **approved** (2026-10-22, "they are fine, but I do not want Italian comments in the
specifications" (translated from Italian)). The human chose to fix this in S8i (S8j review P6, "ok to the
recommendations" (translated from Italian)).

## 1. Affected requirements and acceptance criteria

- **ADR 0012, Decision,** "Conversation key": SHA-256 of the canonical JSON of `system` and the
  first message.
- **SPEC 019,** `edit_args_on_resume` section, "Conversation state", **Key**.
- **PR-021 and PR-024:** wording unchanged. They rely on the key being "the same for every
  request of one conversation" (ADR 0012).
- **No acceptance criterion changes.** A new regression test is added.

## 2. Evidence

- **Claude Code puts a `cache_control` marker on the last block of the request.** At a
  conversation's first request that block is in the first message. From the second request on,
  the first message carries no marker.
- **The key hashes the first message as sent,** marker included. A synthetic check (two requests
  of one conversation, the first with a marker on its only message) gives two different keys.
- **On the developer's timeline** (2026-10-17 simulation, counters only), the second request of
  every conversation looked unknown, and so was counted as a resume. It caused no rewrite,
  because no call is old enough at the second request. It does inflate the resume count, and it
  breaks ADR 0012's stated property.

## 3. Why the current text should change

ADR 0012 requires the key to be the same for every request of one conversation. A marker that
moves is not part of the conversation's identity. It is a caching hint that the client places
where the request ends.

## 4. Proposed change

**ADR 0012 and SPEC 019, Key:**
> SHA-256 of the canonical JSON of `system` and the first message, after every key named
> `cache_control` has been removed from them at any depth. (S8i SCR-003.)

## 5. Impact on tests

- **New regression test:** `test_conversation_key_ignores_cache_markers`. Its docstring names the
  root cause, a marker on the first message at the first request. A marker in `system`, in the
  first message, or in neither gives the same key; a different first message still gives a
  different key.
- `test_conversation_key` is unchanged.

## 6. Impact on architecture

`conversation_key` in the Anthropic adapter changes. No other module is affected.

## 7. Compatibility and migration

- The store is in memory only, so there is nothing to migrate.
- After the upgrade every conversation is unknown once, as after any restart, so its first request
  is a resume.
- No config, API, telemetry or fingerprint change.
