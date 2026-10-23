# S8l SCR-002 — The inject-mode part of AC-KA-3 waits for inject mode

Status: **approved** (2026-10-23, at Gate 2: "I choose b and approve the SCRs" (translated
from Italian)). Applied to the spec and traceability.

## 1. Affected requirements and acceptance criteria

- **SPEC 020 KA-002:** "the auth mode is `inject`" as a reason to keep a conversation.
- **SPEC 020 KA-004:** "in inject mode the credential SHALL be set from the configured source at
  sending time (UP-003)".
- **SPEC 020 AC-KA-3:** its last sentence, "in inject mode it carries the key read at sending
  time".

## 2. Evidence

- **Tokli has no inject mode for Anthropic yet.** SPEC 006 schedules inject mode for S5, which
  is not built. `src/tokli/auth/` holds only the passthrough rules; the configuration schema has
  no `auth` section; every request record says `auth_mode: passthrough`.
- **So the inject clauses cannot be exercised:** there is no configuration that turns inject on,
  and no test can reach that path.

## 3. Why the current text should change

The clauses are not wrong, but AC-KA-3 requires a test that cannot exist until S5. Writing a
skipped or placeholder test would hide the gap (CLAUDE.md §4).

## 4. Proposed change (exact new text)

- **AC-KA-3:** remove the last sentence, and add to SPEC 020: "AC-KA-13 (KA-002, KA-004; from
  the slice that builds inject mode for Anthropic, S5): in inject mode a conversation is kept,
  and its ping carries the key read from the configured source at sending time, not the client's
  header."
- **KA-002 and KA-004:** wording unchanged. Until inject mode exists, every request is
  passthrough, and the inject clauses do not apply.

## 5. Impact on tests

- No existing test changes. The S5 slice adds `test_ping_inject_mode_reads_key_at_send_time`
  (already named in SPEC 020's test scenarios) for AC-KA-13.

## 6. Impact on architecture

- None now. In S5 the keepalive takes the injected key from the same auth component the proxy
  uses (UP-010: auth after rendering, headers only).

## 7. Compatibility and migration

- None.
