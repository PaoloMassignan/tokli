# S8l — Completion report

Status: accepted (Gate 2, 2026-10-23), with SCR-004 applied.

## Requirements implemented

- **SPEC 020:** KA-001…KA-015, KA-001 as changed by SCR-004 (on by default, OAuth included).
  The inject-mode clauses of KA-002 and KA-004 do not apply yet, because Tokli has no inject
  mode (SCR-002, below).
- **SPEC 000:** SC-008 as changed by SCR-004. **SPEC 015:** API-002 as changed by SCR-003.
  **SPEC 006:** UP-002 as changed by SCR-001.
- **SPEC 019:** PR-021 and PR-024 as changed by SCR-001 (`ConversationStore.touch`).
- **SPEC 013:** TC-023…TC-025; TC-013 and TC-015 as changed by SCR-001; schema v6 (ADR 0017).
- **SPEC 014:** OB-014 and the "Keepalive" reason codes (`TOKLI_OBSERVABILITY.md` §4).
- **SPEC 016:** UI-015. **SPEC 017:** "Keys added in S8l", and CF-009 as changed by SCR-001.

## Requirements deferred

- **AC-KA-3, its inject-mode sentence:** no inject mode exists for Anthropic until S5, so no test
  can reach that path. SCR-002 (approved) moved it to the new AC-KA-13, for the slice that
  builds inject mode (S5).

## Spec change requests found in this slice (all approved at Gate 2, 2026-10-23)

- **SCR-002** (above): the inject-mode part of AC-KA-3 waits for inject mode.
- **SCR-003** (`SCR-003-keepalive-money-method.md`): API-002 lists no money method for the
  keepalive's saving and net. The first full run failed the API contract test on this. The
  proposed method `bridged_cache_reads` is implemented, so that the API stays valid; the ping
  cost uses `provider_usage`. Applied to API-002.
- **SCR-004** (`SCR-004-keepalive-on-by-default.md`), requested by the human at Gate 2: the
  keepalive is on by default, for API keys and subscription logins (option B). Applied to
  KA-001, AC-KA-1, SC-008, AC-SC-6, the SPEC 017 defaults, `TOKLI_SCOPE.md`, ADR 0016, the
  README and the user guide. Tests: `test_keepalive_off_sends_nothing`,
  `test_keepalive_on_by_default`, `test_no_originated_requests_when_off` and
  `test_originated_requests_are_keepalives_only` replace the two default-off tests; the
  first two of the new ones failed (RED) before the defaults changed. The tests that relied on
  the old default now set it explicitly (`test_keepalive_eligibility_reasons` for its OAuth
  case, `test_without_ping_the_same_request_is_a_resume`); the UI test expects the toggles on
  at first.

## Tests and evidence

- **RED** (2026-10-23): 27 new or changed tests failed on behaviour, against an interface skeleton
  (the `keepalive` config section, the three record fields, an empty `Keepalive` on
  `Services`). Examples: no `keepalive` attribute in the trace, no ping sent, summary without a
  `keepalive` block, schema version 5 instead of 6, the UI-editable key set. One table in a
  test (`_EXPECTED_SQL`) gained the new annotation `bool | None`.
- **GREEN, then VERIFY:**
  - `pytest` (full suite, with the browser tests, `RUN_BROWSER_TESTS=1`): **1021 passed, 10 skipped** (8 min 43 s, 2026-10-23). The first full
    run had 2 failures, both fixed: the API contract schema (SCR-003) and the doctor goldens (the
    new keys). The skips are the usual environment-gated ones (packaging, provisioned tokenizer
    files, screenshots).
  - `ruff check`, `ruff format --check`, `mypy --strict` (82 source files), `lint-imports`: clean
    (7 contracts kept).
- **New tests:**
  - `tests/integration/test_keepalive.py`: 22 tests, a real Tokli and a scripted fake upstream.
    Only time is faked: one `FakeTime` drives the wall clock of the conversation store and of the
    keepalive, and the keepalive's sleep.
  - `tests/unit/test_metrics_keepalive.py`: 4 tests on hand-built records, among them AC-TC-20
    (60,000 × ($8 − $0.20) per MTok = $0.468).
  - `tests/unit/test_telemetry_store.py::test_schema_migration_v5_to_v6`.
  - `tests/unit/test_config_ui_layer.py::test_s8l_keys_and_defaults`, and the S8l keys in the
    parametrised `test_env_overrides_file_for_every_key`.
  - `tests/ui/test_dashboard.py::test_ui_keepalive_card_and_toggles`.
- **Changed existing tests and fixtures (no weakening):**
  - the API contract schemas gain the summary's `keepalive` block and `keepalive_money_figure`
    (SCR-003);
  - the doctor goldens list the seven new `keepalive.*` keys with their defaults;
  - the schema version assertions now expect v6, and
  the v3→v4 and v4→v5 migration tests leave out the v6 columns when they build their old
  databases; the UI-editable key set includes the two keepalive keys (SCR-001).
- **The test I corrected during GREEN:** `test_keepalive_disabled_at_run_time` first turned the
  feature on with `--set`, which locks the key, so the PATCH that turns it off was refused (409,
  as CF-009 requires). It now turns it on and off through the config API. The browser fixture
  `pinged` first shared its data directory with `fresh`; it now has its own.

## Architecture changes

- **New module** `tokli.app.keepalive` (ADR 0016): one concrete class, one protocol. It uses
  `tokli.upstream`, `tokli.protocols.anthropic_usage`, the conversation store, the telemetry
  store and the trace buffer. These edges are allowed by the layers contract; ARCH §5 gained a
  note.
- **The proxy** calls `begin` when a client request is sent and `end` when it completes; the
  forwarded body and headers are kept on the request's state only while the feature is on, and
  released at `end`.
- **`rebuild`** hands each new configuration to the keepalive (from a worker thread, through
  `call_soon_threadsafe`). The server's shutdown stops every kept conversation.
- **ADR 0017 amended in GREEN:** schema v6 has a third column, `cache_ttl_s`, the request's cache
  lifetime. TC-025 prices a bridged request at the write price of its lifetime, and the lifetime
  was not stored anywhere else. This is a persistence change, recorded in the ADR; it changes no
  behaviour.

## Implementation decisions taken in GREEN

- **A ping with 2xx and no usage** stops the conversation with `upstream_error`, because
  KA-007's success test needs the cache write.
- **The horizon** stops the conversation right after its last ping; that ping's row carries
  `keepalive_stop_reason: horizon`. A developer who comes back after the horizon, but while the
  last ping's cache still lives, is not counted as bridged: the saving is undercounted there,
  never overcounted.
- **Stops without a ping** (`expired`, `evicted`, `disabled`, `shutdown`, `ineligible(…)`) are in
  the log (`event: keepalive_stop`) and, for `ineligible`, in the client request's trace. The
  summary's `stop_reasons` counts only the reasons on ping rows (TC-023 puts the reason on ping
  rows).
- **The ping body** is the held JSON with `max_tokens` replaced, serialised again as compact JSON
  (ADR 0016 wording updated).
- **The Recent requests list** shows ping rows (outcome `keepalive`), so a ping can be inspected
  like any request. The summary, time series, overhead and compressor figures leave them out.

## Measured performance

- Not measured separately. On a client request the keepalive adds two dictionary operations;
  the pings run on the event loop and are shown not to delay a client request
  (`test_ping_does_not_delay_client_requests`, a 5 s ping against a client request under 2 s).

## Real-traffic replay

- Not applicable: S8l adds no compressor. The real-use check of the test plan (a day with the
  feature opted in, with the keepalive block and the stop reasons) needs the human's consent and
  real credentials, and has **not** been run.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] New code paths emit spans with durations: `keepalive`, `upstream`, `usage` per ping.
- [x] New decisions use reason codes from §4: the "Keepalive" row, extended by spec change.
- [x] New telemetry fields are in the schema (v6), the request API view and the retention job
  (ping rows are ordinary rows).
- [x] Credential and content scans cover the new paths
  (`test_keepalive_never_persists_content_or_credentials`, `test_keepalive_trace_and_log_line`).
- [x] The recent-request view shows the pings.

## Known limitations

- **On by default without a real-use check** (SCR-004, the human's decision): a user who
  upgrades starts sending keepalive requests; with a subscription they count towards the
  plan's usage. The release notes must say so.

- **OAuth tokens held for hours** (E12 (d)) are untested; a rejected token stops the keepalive
  with `auth_rejected`, which the real-use check will show.
- **The bridged count is conservative** after the horizon (above).
- **A ping in flight when a client request arrives** is cancelled with its task; it leaves no
  row.

## Unresolved questions

- None. The real-use check (a day with OAuth) is still to be run, with the human's consent.

## Gate 2 record

- 2026-10-23: "I accept, I want the ping on by default", then "I choose b and approve the
  SCRs" (both translated from Italian). SCR-002, SCR-003 and SCR-004 (option B) approved and
  applied; the full suite was run again after SCR-004 (below).

## Verification after SCR-004 (2026-10-23)

- The first full run after SCR-004 had 2 failures:
  - `test_reason_codes_closed_set`: a real bug. The keepalive reason codes were listed in
    `TOKLI_OBSERVABILITY.md` §4 but missing from the closed set in `tokli.observability.reasons`.
    With the feature off by default no trace carried them. Regression test first
    (`test_keepalive_reason_codes_are_known`, failed), then the fix (the `KEEPALIVE` set).
  - `test_ui_flags_compressor_not_applying`: passed alone (3 of 3). Its fixture now lifts the
    request budget, as other compression-asserting tests do; the probable cause, a cold request
    over 50 ms under load, is not proven.
- `pytest` (full suite, browser tests included): **1024 passed, 10 skipped** (9 min 44 s).
  `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` (7 contracts): clean.
