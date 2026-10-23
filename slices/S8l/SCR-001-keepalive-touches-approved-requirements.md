# S8l SCR-001 — The cache keepalive touches six approved requirements

Status: **approved** at S8l Gate 1 (2026-10-23, "I approve" (translated from Italian)).

## 1. Affected requirements and acceptance criteria

| Spec | Requirement | Approved for | Change |
|---|---|---|---|
| SPEC 006 | UP-002 | S1 | passthrough credentials may be held in memory for a kept conversation |
| SPEC 019 | PR-021 | S8c, changed by S8i SCR-001 | a successful ping counts as the conversation's last request |
| SPEC 019 | PR-024 | S8c, changed by S8i SCR-001 | the stored time is that of the last request or successful ping |
| SPEC 013 | TC-013 | S3 | the overhead distribution leaves out keepalive rows |
| SPEC 013 | TC-015 | S3 | the token totals leave out keepalive rows |
| SPEC 017 | CF-009 | S4, changed by S8a SCR-001 | `keepalive.enabled` and `keepalive.oauth` are UI-editable |
| ADR 0012 | store contents and resume rule | S8c, amended twice | amendment 3: the store's time follows a successful ping |

No existing acceptance criterion changes. New ones: SPEC 020 AC-KA-10 (PR-021, PR-024),
AC-KA-11 (UP-002), SPEC 013 AC-TC-20 (TC-013, TC-015), SPEC 016 AC-UI-6 (CF-009).

## 2. Evidence

- **E12** (`TOKLI_EVIDENCE.md`, 2026-10-22): a ping must repeat the last forwarded request,
  credentials included, more than 55 minutes after it. Passthrough credentials exist only in the
  client's request, so Tokli must hold them until the ping.
- **E12, the pinged returns:** 110 minutes after the last client request the cache was warm. Under
  the current PR-021 the same request is a resume (more than 3,600 + 60 s since the conversation
  was last seen), so `edit_args_on_resume`, when on, would stub old edit arguments and rewrite a
  prefix the ping just kept warm: the keepalive's saving would be lost, and the stubs would be
  sent for no reason.
- **Keepalive rows** have usage and timings but no token estimates and no Tokli overhead. Counted
  in TC-013 and TC-015 they would change totals that describe compression, and the summary
  would no longer equal the same traffic without the keepalive.

## 3. Why the current requirements should change

- **UP-002** forbids storing credentials "beyond the lifetime of the request". Without holding
  them, no ping is possible in passthrough mode, which is the mode the developer uses.
- **PR-021 and PR-024** define a resume by the last client request. After a successful ping the
  cache is warm, so the request is not a resume in the sense SPEC 019 means (the cache expired).
- **TC-013 and TC-015** would mix keepalive rows into compression figures.
- **CF-009** lists the UI-editable keys, and the human asked for dashboard toggles (S8l review P6).

## 4. Proposed change (exact new text)

- **UP-002:** "WHILE a provider's auth mode is `passthrough`, THE SYSTEM SHALL forward the
  client's credential headers unchanged and SHALL NOT store them beyond the lifetime of the
  request, except that it SHALL hold them in memory for a kept conversation of SPEC 020 (KA-003),
  until that conversation stops being kept. (S8l SCR-001.)"
- **PR-021:** "WHEN a request's conversation (key per ADR 0012) is not known to Tokli, OR was last
  seen more than its cache lifetime (PR-027) plus `pruning.resume_margin_s` seconds ago, THE
  SYSTEM SHALL treat the request as a resume; otherwise it SHALL NOT. A conversation is last seen
  at its last request or at its last successful keepalive request (SPEC 020 KA-007, KA-013),
  whichever is later. (S8i SCR-001, S8l SCR-001.)"
- **PR-024:** "THE conversation store SHALL keep, per conversation key, only the time the
  conversation was last seen (PR-021), the `cache_ttl_s` of its last request (S8i SCR-001) and
  the pruned call ids; it SHALL be bounded by `pruning.conversation_states` with
  least-recently-used eviction, and SHALL NOT be written to disk. (S8l SCR-001.)"
- **TC-013:** the first sentence becomes "THE metrics API SHALL report the Tokli overhead
  distribution (…) per request-size bucket (…), per policy and per `config_hash`, over client
  requests only (keepalive rows, TC-023, are left out)." The rest is unchanged.
- **TC-015:** the first sentence becomes "THE metrics API SHALL compute token totals over client
  requests of transformable endpoints only (verbatim routes count in request totals by outcome,
  never in token figures; keepalive rows, TC-023, count only in TC-025), …". The rest is
  unchanged.
- **CF-009:** "v1 UI-editable keys: `compressors.<id>.enabled`,
  `compressors.<id>.apply_to_verbatim_tools` (where it exists), `telemetry.retention_days`,
  `keepalive.enabled`, `keepalive.oauth`. (S4 SCR-001: there is no policy key. S8a SCR-001: the
  verbatim opt-in. S8l SCR-001: the keepalive toggles.)"
- **ADR 0012, amendment 3:** the store's time is the later of the last request and the last
  successful ping; nothing else in the store changes, and the store still holds no content.

## 5. Impact on tests

- Existing tests for UP-002, PR-021, PR-024, TC-013, TC-015 and CF-009 keep passing unchanged:
  with the keepalive off (the default) the behaviour is the same.
- New: `test_successful_ping_prevents_resume` (AC-KA-10),
  `test_keepalive_never_persists_content_or_credentials` (AC-KA-11),
  `test_keepalive_rows_excluded_from_totals` (AC-TC-20), `test_ui_keepalive_card_and_toggles`
  (AC-UI-6), and the UI-editable keys in `test_ui_override_only_when_not_pinned`.

## 6. Impact on architecture

- The keepalive component (app layer) tells the conversation store of a successful ping. It is a
  new call into an existing app-layer module, not a new dependency direction. The timer-driven
  upstream calls are ADR 0016.

## 7. Compatibility and migration

- Config: two new UI-editable keys, both off by default; UI overrides of earlier versions stay
  valid.
- Telemetry: schema v6 (ADR 0017). Summaries over ranges without keepalive rows are unchanged.
- `config_hash`: unchanged, because the `keepalive` section is not part of it (SPEC 017).
