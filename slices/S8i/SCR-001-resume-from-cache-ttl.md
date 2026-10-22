# S8i SCR-001 — A resume follows the cache lifetime the client asked for

Status: **approved** at S8i Gate 1 (2026-10-16, "the specifications are fine" (translated from Italian)).

## 1. Affected requirements and acceptance criteria

| Spec | Requirement | Change |
|---|---|---|
| SPEC 019 | PR-021 (approved for S8c) | changed |
| SPEC 019 | PR-024 (approved for S8c) | the store also keeps the last request's `cache_ttl_s` |
| SPEC 019 | PR-027, PR-028 | new |
| SPEC 019 | AC-PR-17…AC-PR-19 | new |
| SPEC 003 | AN-011 | new |
| SPEC 001 | data model: `CanonicalRequest.cache_ttl_s` | new |
| SPEC 009 | CC-006 (changed for S8c) | the conversation state includes the previous request's cache lifetime |
| SPEC 017 | `pruning.resume_after_s` | replaced by `pruning.cache_ttl_default_s` and `pruning.resume_margin_s` |
| SPEC 017 | CF-013 | new (renamed keys) |
| ADR 0012 | resume rule and store contents | amended |

AC-PR-11…AC-PR-16 keep their wording. AC-PR-11's "two hours" and "one hour minus a second"
still hold with a 1 h TTL and a 60 s margin.

## 2. Evidence

- **The provider's cache lifetime is chosen by the client.** In Anthropic Messages, every
  `cache_control` marker has a `ttl` of `"5m"` (the default when absent) or `"1h"`. A cached
  prefix expires when no request has read it for that long. Every read refreshes it.
- **The human's traffic** (Tokli telemetry, last 7 days, counters only):
  - 2.32 M of the 2.53 M cache-write tokens were 1 h writes;
  - the rest were 5 min writes;
  - 22 requests read nothing from the cache, and they wrote 68 % of all cache writes;
  - nearly all followed a pause of more than an hour (`slices/S8i/SPEC_REVIEW.md` §0).
- **Today PR-021 uses one fixed number,** `pruning.resume_after_s` (3,600 s), for every client:
  - for a client that asks for 5 minutes, the cache is gone after 5 minutes, but Tokli waits an
    hour before it treats a request as a resume;
  - for a client that asks for 1 hour, Tokli acts at exactly the moment the cache may still
    exist (the TTL is a maximum; no margin).

## 3. Why the current requirement should change

- **It guesses a value that the request states.** A wrong guess either misses resumes (5 min
  clients) or acts at the edge of a warm cache (1 h clients, no margin). In the second case a
  prune costs one extra cache write (ADR 0012, Consequences).
- **The time cannot be decided per file.** The provider caches the prefix up to a breakpoint, and
  every read refreshes all of it. A resume therefore stays a per-conversation decision
  (S8i review §1).

## 4. Proposed change (exact new EARS text)

**SPEC 019:**

> **PR-021** WHEN a request's conversation (key per ADR 0012) is not known to Tokli, OR was last
> seen more than its cache lifetime (PR-027) plus `pruning.resume_margin_s` seconds ago, THE
> SYSTEM SHALL treat the request as a resume; otherwise it SHALL NOT. (S8i SCR-001.)

> **PR-027** THE cache lifetime of a conversation SHALL be the `cache_ttl_s` (AN-011) of its
> previous request, or, when that is absent, the default for the request's protocol in
> `pruning.cache_ttl_default_s`. (S8i SCR-001.)

> **PR-028** THE SYSTEM SHALL record in each request's trace whether the request is a resume, the
> cache lifetime used, its source (`previous_request`, `protocol_default`, or `unknown_conversation`)
> and the seconds since the conversation's previous request (absent when unknown). (S8i SCR-001.)

**SPEC 003:**

> **AN-011** THE adapter SHALL set `cache_ttl_s` on the canonical request to the longest lifetime
> among the `cache_control` markers in `system`, `tools` and `messages`: 300 for a marker of
> `type: "ephemeral"` without `ttl` or with `ttl: "5m"`, and 3,600 for `ttl: "1h"`. WHEN the
> request has no marker, or any marker has another `type` or `ttl`, THE adapter SHALL leave
> `cache_ttl_s` absent, and in the second case SHALL record the reason code
> `cache_ttl_unrecognised` in the trace. (S8i SCR-001.)

Rationale of "any unrecognised marker leaves it absent": a lifetime Tokli does not understand
could be longer than 1 h. Then the protocol default applies, which is the current behaviour.

**SPEC 009, CC-006,** the last sentence becomes:
> … except that a request-scope compressor MAY depend on the conversation state of SPEC 019
> PR-021…PR-024 and PR-027 (whether the request is a resume, and the replacements decided at the
> conversation's last resume), received read-only from the engine (S8c, S8i SCR-001,
> ADR 0012).

**SPEC 017 keys,** "Keys changed in S8i":

| Key | Default |
|---|---|
| `pruning.cache_ttl_default_s` | `{anthropic_messages: 3600}`: the protocol, when the request states no lifetime Tokli understands (S8i P2). One entry per protocol with an adapter. |
| `pruning.resume_margin_s` | `60` (S8i P3) |
| `pruning.resume_after_s` | removed; renamed to `pruning.cache_ttl_default_s.anthropic_messages` (CF-013) |

**SPEC 017:**

> **CF-013** WHEN a layer sets a key listed in "Renamed keys", THE SYSTEM SHALL use its value for
> the new key, SHALL print a warning naming the layer, the old key and the new key at startup and
> in `tokli doctor`, and SHALL refuse to start (CF-003) if the same layer also sets the new key.

| Old key | New key | Since |
|---|---|---|
| `pruning.resume_after_s` | `pruning.cache_ttl_default_s.anthropic_messages` | S8i |

**SPEC 019 acceptance criteria:**

> **AC-PR-17** (PR-021, PR-027): the previous request carried `ttl: "1h"`; 3,661 s later → a
> resume; 3,660 s later → not (as corrected by SCR-002). The previous request carried markers without `ttl`; 361 s later →
> a resume; 360 s later → not.

> **AC-PR-18** (AN-011, PR-027): a request with markers `"5m"` and `"1h"` has `cache_ttl_s`
> 3,600. A request with no marker, or one marker with `ttl: "24h"`, has none: the next request
> uses `cache_ttl_default_s.anthropic_messages` (3,600), and the second case traces
> `cache_ttl_unrecognised`.

> **AC-PR-19** (PR-028, CF-013): the trace of a resume and of a non-resume carries the four
> attributes. A config file that sets `pruning.resume_after_s: 120` gives
> `cache_ttl_default_s.anthropic_messages = 120` and a warning; setting both keys in one file
> refuses to start.

## 5. Impact on tests

- **New:**
  - `test_adapter_exposes_cache_ttl`;
  - `test_resume_uses_previous_request_ttl_1h`;
  - `test_resume_uses_previous_request_ttl_5m`;
  - `test_resume_longest_ttl_wins`;
  - `test_resume_without_cache_marker_uses_protocol_default`;
  - `test_resume_unknown_ttl_uses_protocol_default_and_traces`;
  - `test_resume_trace_attributes`;
  - `test_renamed_key_resume_after_s`.
- **Changed because the spec changes** (no assertion weakened):
  - the config-loader key tables (`pruning.resume_after_s` → the two new keys);
  - the pinned default `config_hash`;
  - the two doctor goldens;
  - `test_resume_pruning.py`, whose clock now meets the margin. Its assertions on "two hours"
    and "one hour minus a second" stay.
- **Kept unchanged:** `test_unknown_conversation_is_resume`, and AC-PR-12's stability between
  resumes.

## 6. Impact on architecture

- **The conversation store** (`tokli.app`) keeps the previous request's `cache_ttl_s` next to its
  time. It stays in memory and LRU-bounded, with no disk format.
- **The resume decision moves out of the pruner.** A helper next to the store makes it, and the
  engine passes `is_resume` to the request-scope pruners in the read-only conversation view.
  `edit_args_on_resume` no longer receives `resume_after_s`. No new dependency direction: the
  adapter fills a canonical-request field that `tokli.app` reads.
- **ADR 0012 amendment:** the resume rule, the store's contents, and the trace attributes.

## 7. Compatibility and migration

- **Config:** `pruning.resume_after_s` keeps working through CF-013, with a warning.
- **The UI overrides file** cannot hold it, because the key is not UI-editable (CF-009).
- **`config_hash`:** it changes for every user, because the `pruning` section changes. Telemetry
  groups by `config_hash`, so the dashboard shows a new configuration group from the upgrade on.
- **Telemetry schema, API, fingerprint:** unchanged. The new facts go to the trace only.
- **Behaviour:**
  - with Claude Code's 1 h lifetime, a resume now needs 60 s more pause than before;
  - with a 5 min lifetime, resumes happen after about 6 minutes instead of an hour;
  - `edit_args_on_resume` and its stability between resumes (PR-023) are otherwise unchanged.
