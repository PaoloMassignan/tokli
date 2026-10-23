# S8l SCR-004 — The cache keepalive is on by default

Status: **approved** (2026-10-23). Requested by the human at Gate 2: "I accept, I want the ping
on by default"; then, on the open choice: "I choose b and approve the SCRs" (both translated
from Italian). Option B applies: on by default for API keys and subscription logins.

## 1. Affected requirements and acceptance criteria

- **SPEC 020 KA-001** and **AC-KA-1**: off by default.
- **SPEC 000 SC-008** and **AC-SC-6**: with the default configuration, Tokli originates no request.
- **SPEC 017** "Keys added in S8l": the defaults of `keepalive.enabled` and `keepalive.oauth`
  (both `false`).
- **`TOKLI_SCOPE.md`**, the "Cache keepalive" row: "Off by default".
- Unchanged: KA-002…KA-015, UI-015 (the card already shows while the feature is on; the Settings
  text already says what Tokli does and holds), CF-009 (both toggles stay UI-editable).

## 2. Evidence

- E12 (`TOKLI_EVIDENCE.md`): a `max_tokens: 1` ping read the whole 64k prefix and wrote nothing;
  the pinged return was warm and the control return was cold.
- The S8l simulation (`slices/S8l/SPEC_REVIEW.md`): one-hour keepalives up to 12 h saved about
  23 % of the spend, net of the pings.
- Not yet measured: a day of real use with the feature on, and whether an OAuth token held for
  hours is still accepted (E12 (d)).

## 3. Why the requirement should change

The human decides the default (product decision). With the feature off, a user who never opens
Settings gets none of the saving.

## 4. Proposed change (exact new text)

- **KA-001:** "WHILE `keepalive.enabled` is false, THE SYSTEM SHALL keep no conversation and send
  no keepalive request. `keepalive.enabled` and `keepalive.oauth` are true by default. (S8l
  SCR-004.)"
- **AC-KA-1:** "with `keepalive.enabled` false, after a cached 1 h request and 2 h of fake time,
  the fake upstream has received only the client's request, and the conversation store holds no
  keepalive state; with the default configuration and an eligible request with an OAuth
  credential, a ping is sent." (As applied, the first sentence keeps the original wording.)
- **SC-008:** "THE SYSTEM SHALL originate upstream requests only as the keepalive requests of
  SPEC 020, and only while `keepalive.enabled` is true (the default, S8l SCR-004)."
- **AC-SC-6:** "with `keepalive.enabled` false, no upstream request is sent that a client did not
  send, over every compat fixture and 2 h of fake time; with the default configuration, every
  originated request is a keepalive request (`max_tokens` 1, or the thinking budget + 1) of a
  conversation a client request was sent in."
- **SPEC 017:** `keepalive.enabled` | `true` and `keepalive.oauth` | `true` (S8l SCR-004).
- **Option A (not chosen): `keepalive.oauth` stays `false`.** On by default for API keys, where
  the saving is money; subscription logins stay an opt-in until the real-use check shows that a
  token held for hours is accepted and that pings do not eat into the plan's usage limits
  noticeably.
- **Option B (chosen): `keepalive.oauth` default `true` as well.** On for everyone; a rejected token
  stops the keepalive with `auth_rejected` (KA-008).
- **`TOKLI_SCOPE.md`:** "On by default, for API keys and subscription logins (S8l, SPEC 020,
  SCR-004)…".

## 5. Impact on tests

- `test_keepalive_off_by_default_sends_nothing` becomes `test_keepalive_off_sends_nothing`
  (sets `keepalive.enabled` false) plus `test_keepalive_on_by_default` (default config, one
  ping).
- `test_no_originated_requests_by_default` becomes `test_no_originated_requests_when_off`
  (sets `keepalive.enabled` false), and `test_originated_requests_are_keepalives_only` asserts,
  over the compat fixtures and an eligible conversation, that every originated request is a
  client body with only `max_tokens` changed.
- `test_keepalive_eligibility_reasons` sets `keepalive.oauth` false for its `oauth_not_enabled`
  case; `test_without_ping_the_same_request_is_a_resume` ("with the keepalive off") sets
  `keepalive.enabled` false; the UI test expects both toggles on at first and the card shown
  until the feature is turned off.
- `test_s8l_keys_and_defaults`, the doctor goldens and the UI test expect the new default(s).
- Existing integration and compat tests that count upstream requests over fake time are
  checked; none is weakened.

## 6. Impact on architecture

None. The keepalive already exists in every build; only its default changes.

## 7. Compatibility and migration

- **Users who upgrade** start sending pings without having switched anything on. For API-key
  users these cost money (about 1/40 of the write each avoids); for subscription users they
  count towards the plan's usage. `README.md` and `docs/GETTING_STARTED.md` §5 say so, and how
  to turn it off; the release notes must too.
- No schema, API or `config_hash` change (the `keepalive` section is not in `config_hash`).
