# S8i — Spec review: the resume follows the provider's cache lifetime

Status: **Gate 1 passed (2026-10-16), Part A only.** Erratum SCR-002 (AC-PR-17 boundary) approved 2026-10-16 ("yes" (translated from Italian)).
Part B (outlines of old reads) was set aside by the human on 2026-10-16.
Requested by the human on 2026-10-16 ("generate specifications following the process, using
the cache lifetime given (translated from Italian)), after a counters-only analysis of their recent Claude Code traffic.

**Slice scope (proposed).**
- **Part A, the resume rule:** a request is a resume when the provider's cache for its
  conversation has expired. The cache lifetime is the one the client asked for in the request,
  not a fixed number of seconds. This changes PR-021 (approved for S8c), so it goes through
  `SCR-001-resume-from-cache-ttl.md` (to be written once P1…P3 are answered).
- **Part B, a new pruner `reads_on_resume`:** at a resume, old `Read` results become an outline
  that keeps chosen lines verbatim, instead of the full file. It is gated by a pre-code
  experiment, **E10(f)**, because every earlier form of this lever drew provider refusals
  (E10(c), E10(d)).

**Specs in scope:**
- SPEC 019: PR-021 (changed through the SCR), and new requirements PR-040 onwards;
- SPEC 003: the adapter exposes the request's cache lifetime;
- SPEC 009: CC-006 (the state now includes the cache lifetime);
- SPEC 010: a catalogue row and the assumption `outline_suffices_until_reread`;
- SPEC 012: a smoke family;
- SPEC 017: the keys;
- ADR 0012: an amendment.

**Explicitly out of scope:**
- Shell commands that read files (`cat`, `sed -n`, `Get-Content` through `Bash`/`PowerShell`).
  The human asked to discuss them after this slice. They are the larger volume (see §0).
- Tool-call arguments: E10(c) showed refusals.
- Summaries written by a model: that would be a compressor of the `expensive` cost class, listed
  under "Later".

## 0. Evidence behind the slice (counters only, 2026-10-16)

The human's sessions of the last 7 days (13 sessions, 61 pauses of more than one hour), plus
Tokli's telemetry for the same days. The tools are throwaway scripts in the session's scratch
directory. They printed aggregates only.

**Pauses dominate the cache-write cost.**
- 22 of 312 forwarded requests read nothing from the cache.
- They wrote 1.71 M tokens, **68 % of all cache writes**.
- Nearly all of them followed a pause of more than an hour.
- At Opus 5.5 prices, cache writes (about $20) cost more than cache reads (about $11).

**Context held at the 61 restarts** (rebuilt from transcripts; an upper bound, see the limits
below):

| Part | Tokens | Share |
|---|---|---|
| `Bash` results | 3.98 M | 36.8 % |
| `Edit`/`Write` arguments | 3.73 M | 34.5 % |
| Other tool arguments | 1.60 M | 14.8 % |
| Human text | 0.55 M | 5.1 % |
| Assistant text | 0.47 M | 4.3 % |
| **`Read` results** | **0.28 M** | **2.6 %** |

**`Read` results at a restart:**
- 91 % are of files that no `Read`/`Edit`/`Write` touches again in the rest of the context;
- 3.4 % are superseded in the PR-007 sense;
- 79 % are more than 2 hours old.

**Limits:**
- The transcripts include sessions that did not go through Tokli. Tokli's telemetry sees 22 cold
  requests and 1.7 M rewritten tokens, against the 61 restarts and 10.8 M tokens rebuilt here.
- "Not touched again" ignores reads through shell commands, so it overstates what is unused.

**Consequence for the value of Part B:** on this traffic, Part B acts on at most about 2.6 % of
the context rewritten at a restart. That is roughly $2 a week at the 1 h cache-write price,
before the outline's own size. Its main value is the mechanism and the experiment, which the
shell-read follow-up would reuse. This is product question P4.

## 1. Ambiguities

| Req | Question | Proposed reading |
|---|---|---|
| PR-021 | "Last seen more than `resume_after_s` ago": which lifetime applies when the client marks breakpoints with different TTLs in one request? | The longest TTL among the request's `cache_control` markers. A prefix is still warm while its longest-lived breakpoint is. |
| PR-021 | Is the TTL that of the **previous** request (which wrote the cache) or of the current one? | The previous request's, kept in the conversation state. It falls back to the current request's when the conversation is unknown. |
| PR-021 | A request with no `cache_control` at all | Its conversation has no cache to lose. Use the protocol's fallback `pruning.cache_ttl_default_s.<protocol>` (P2). |
| PR-021 | `ttl` absent from a marker | The protocol's default: 5 minutes for Anthropic Messages. A `ttl` value Tokli does not recognise uses the protocol's fallback and is traced. |
| PR-021 | Can one file "expire" while its conversation is still warm? | No. The provider caches the **prefix** up to a breakpoint, and Claude Code places its breakpoint on the latest messages. Every request that reads the cache refreshes the whole prefix, including an old file in it. Changing that file while the cache is warm would make the provider write everything after it again. So *when* to prune stays a per-conversation decision (the resume). *What* to prune is decided per file (P5). |
| PR-040 | What makes a `Read` "old"? | **Per file** (P5): the file has not been touched (read, edited or written) in the last `resume_min_age_turns` (4) human turns. A file that was read early but edited recently stays whole. |

## 2. Contradictions

- **The roadmap and S8c on `edit_args_on_resume`:**
  - S8c closed with the pruner "off and not recommended" because of refusals (E10(c)).
  - The human's effective configuration has it **on**: Tokli's telemetry shows 125 accepted
    replacements in 7 days.
  - Part A makes resumes more frequent for 5-minute clients, so the risk grows for them. For the
    human's 1-hour traffic it is unchanged.

  This is not a spec contradiction, but the human should decide (P6).
- **SPEC 019, design decision 1** ("Content-level stubbing, not structural removal") stays valid:
  an outline replaces content only.

## 3. Missing behaviour

- **TTL in the adapter:** SPEC 003 does not expose the TTL of `cache_control` markers. Today the
  adapter only records that a breakpoint exists (`cache_breakpoint_after`).
- **Trace:** nothing yet records why a request was or was not a resume, or with which lifetime.
- **OpenAI protocols** carry no TTL. With S5 and S7 (not built yet), the fallback applies. This
  is not in scope here.

## 4. Portability concerns

- Wall-clock time only, as in ADR 0012.
- The outline's line rules are regular expressions over text. They need CRLF-aware line splitting,
  and Claude Code's `"{n}\t"` numbering must be kept (PR-032 already handles both styles).
- No new file or encoding.

## 5. Observability requirements for this slice

- **Trace attributes per request:**
  - `resume: bool`;
  - `cache_ttl_s` (the lifetime used);
  - `cache_ttl_source` ∈ `{previous_request, request, fallback}`;
  - `since_last_s` (rounded to seconds).

  These are counters only.
- **Reason codes:**
  - `not_applicable(not_resume)` (exists);
  - `not_applicable(too_recent)` (exists);
  - `not_applicable(no_outline_lines)`;
  - `not_applicable(not_whole_read)`;
  - `not_applicable(below_min_tokens)`.
- **Telemetry:** no schema change. `history_rewritten` already marks the requests a resume
  changed.
- **Checklist:** TOKLI_OBSERVABILITY §8 is run at Verify.

## 6. Architectural risks

- **The conversation store gains the last request's TTL.** It is in memory, bounded, with no
  disk format. ADR 0012 gets an amendment.
- **The resume rule becomes one shared helper.** Two pruners now use it, which justifies the seam
  (CLAUDE.md §5). The decision stays in the engine's read-only conversation view (CC-006). The
  pruners only read `is_resume`.
- **The store keeps the pruned ids per pruner.** Today there is one set, for
  `edit_args_on_resume`. A second pruner needs its own set: S8d planned the same amendment.
- **No new dependency.** No new dependency direction: the adapter adds a field to the canonical
  request, and the store reads it in `tokli.app`.

## 7. Product questions → for the human

1. **P1 — Which lifetime decides a resume?** **Answered 2026-10-16 ("Ok"):**
   - the cache lifetime defined by the protocol, as the client chose it in the conversation's
     previous request;
   - for Anthropic Messages, that is the longest `cache_control` TTL: "1h" = 3,600 s, absent or
     "5m" = 300 s;
   - it is applied with a margin (P3);
   - it falls back to the current request's TTL when the conversation is unknown.
2. **P2 — A request without any cache marker,** or with a TTL Tokli does not know.
   **Answered 2026-10-16 ("Ok"):** a **default per protocol**,
   `pruning.cache_ttl_default_s.<protocol>`, replaces the single `pruning.resume_after_s`:
   - `anthropic_messages`: 3,600 s, the current value. This applies to requests without any
     marker or with an unknown TTL. A marker without `ttl` is not covered here: it is 300 s by
     the protocol (P1).
   - The OpenAI protocols (S5, S7, not built yet): their caching is automatic and carries no TTL
     in the request. Their defaults are set when those adapters exist. Until then the key holds
     only `anthropic_messages`.
   - Migration: `pruning.resume_after_s` is removed. A user value for it is migrated to
     `pruning.cache_ttl_default_s.anthropic_messages` with a warning (SPEC 017, to be detailed in
     the SCR).
3. **P3 — The margin.** Recommended: **60 s** (`pruning.resume_margin_s`), applied to every TTL.
   Anthropic guarantees at most the TTL, so any margin is safe, and a longer one only delays the
   saving. For "5m" a 5-minute margin would double the wait.
4. **P4 — Part B on `Read` only?** Its value on your traffic is small (§0, about 2.6 % of a
   restart's context).
   - (a) **Do Part A, and run E10(f) for Part B.** Build B only if E10(f) passes; its experiment
     and mechanism are what the shell-read follow-up needs. **Recommended.**
   - (b) Part A only; Part B together with the shell-read follow-up.
   - (c) Part A, plus Part B extended now to `cat`/`Get-Content` through the shell (larger
     volume, but you asked to discuss it later).
5. **P5 — The outline, if B goes ahead.**
   - **What it keeps verbatim,** with their line numbers in the file's own numbering style:
     - the declaration lines (classes, functions, methods, top-level assignments), matched by
       language rules chosen from the file extension (`pruning.outline_rules`);
     - the first `outline_head_lines` (10) lines.
   - **Each omitted run** becomes one note:
     `[tokli: lines <a>-<b> omitted — read the file again for them]`.
   - **Applies to:** `Read` results that are whole reads, at least `resume_result_min_tokens`
     (500) tokens, and not errors, of a file that is **old per file**. A file is old when no
     tool record has read, edited or written its path (normalised as in SPEC 019) in the last
     `resume_min_age_turns` (4) human turns. **Answered 2026-10-16 ("Ok") for the per-file rule.**
   - **Still open:** the thresholds and the outline form. Recommended: these defaults, decided
     again from the E10(f) result.
6. **P6 — `edit_args_on_resume` is on in your configuration,** although S8c measured more
   refusals with it (17 of 66 against 6 of 66). Recommended: **switch it off** (a user setting;
   the human decides and changes it). It is independent of this slice, but Part A also changes its
   resume moments.
7. **P7 — Run E10(f) before any code.** See §10: about 120 calls on `claude-opus-5-5`, a few
   dollars, run by the human with their key. Recommended: **yes**, with the same decision rule as
   S8d.

## 8. Implementation decisions → decided by Claude (recorded, not asked)

- The TTL is parsed in the Anthropic adapter as an optional `cache_ttl_s` on the canonical
  request: the maximum over `system`, `tools` and message blocks. Unknown values give `None`.
- The conversation store keeps `last_ttl_s` next to `last_seen`. LRU, bound and keys are
  unchanged.
- The per-protocol fallback is read from config by protocol id. A protocol with no entry has no
  fallback, which config validation rejects for every protocol that has an adapter.
- The per-file age uses the resource keys of `analyze.tool_resources` when that analyzer exists
  (S8a-3). Until then a small path extractor reads `file_path`/`notebook_path` from the Claude
  Code file tools of the default tool semantics (SPEC 019), with the same normalisation. One
  concrete function, no new seam.
- The helper `resume_decision(state, request, config) -> ResumeDecision(is_resume, ttl_s, source,
  since_s)` lives in `tokli.app` next to the store. Both pruners read `is_resume` from the
  engine's view.
- Outline rules are config data, keyed by extension: Python, C#, Java/Kotlin,
  TypeScript/JavaScript, Go, Rust, plus a default rule that keeps only the head. Tests cover each
  rule on synthetic files.
- The outline keeps protected spans verbatim and in order, like PR-015, and the result's own
  numbering style, like PR-032.
- Between resumes, the outline decided at the last resume is re-applied to the same calls
  (PR-023). It is a pure function of the original text and the config, so it is byte-identical.

## 9. Test plan (req/AC → tests)

**Part A:**

| Req / AC | Tests |
|---|---|
| PR-021 as changed | `test_resume_uses_previous_request_ttl_1h` (3,600 s + 60 s → resume; 3,600 s + 59 s → none); `test_resume_uses_previous_request_ttl_5m` (360 s → resume; 359 s → none); `test_resume_longest_ttl_wins`; `test_resume_without_cache_marker_uses_protocol_default`; `test_resume_unknown_ttl_uses_protocol_default_and_traces`; `test_resume_after_s_migrated_to_protocol_default`; `test_unknown_conversation_is_resume` (exists, kept) |
| SPEC 003 addition | `test_adapter_exposes_cache_ttl` (system, tools and message blocks; absent → 300; unknown → none) |
| Observability | `test_resume_trace_attributes` |

**Part B** (only if E10(f) passes):

| Req / AC | Tests |
|---|---|
| Outline | `test_outline_keeps_declarations_and_head_verbatim`, one per language rule |
| Applicability | `test_outline_only_at_resume_and_old_whole_reads`; `test_outline_skips_partial_reads_errors_small` |
| Per-file age | `test_outline_file_touched_recently_stays_whole` (read at turn 1, edited at turn 8 of 10: not outlined); `test_outline_file_untouched_is_outlined`; `test_outline_path_normalisation` |
| Stability between resumes | `test_outline_stable_between_resumes` |
| Protected spans and numbering | `test_outline_keeps_protected_spans`; `test_outline_numbering_styles` |
| Reference integrity | `test_outline_rejected_on_reference_target` (CC-019) |
| Structure | `test_outline_preserves_structure` |
| Defaults | `test_reads_on_resume_off_by_default`; `test_lossless_only_switches_it_off` |

**Evaluation and replay:**
- the smoke family `reread_after_outline` (SPEC 012), checker `answer_or_read`;
- the real-traffic replay counters, with the human's consent.

## 10. E10(f) — do outlines of old reads draw refusals? (before code)

**Script:** `evals/experiments/e10f_read_outlines.py`, to be written after Gate 1, in the form of
E10(d).

**The conversation** (synthetic):
- the agent reads a source file of about 200 lines with `Read`, in Claude Code's numbering;
- five unrelated exchanges follow;
- the user asks a question;
- half of the questions are answerable from the declarations (a signature, a class name), half
  only from a function body (a constant inside it).

**Forms of the old result:**
- `original` (control);
- `outline` (P5);
- `head` (first 10 lines plus one note);
- `descriptive` (the E10(d) stub, as a reproduction check).

**Size:** 15 cases (Python and C#) × 2 repetitions × 4 forms = 120 calls. Recorded per call:
`stop_reason`, the outcome (`pass` = right answer or a `Read` of the right file; `fail`;
`refusal`) and the request input tokens.

**Decision rule (as S8d):**
- **Go** for the `outline` form if it has no more refusals than the control (within 1 of 30) and
  no wrong answers.
- **Otherwise** Part B stops, and the result goes into TOKLI_EVIDENCE §2.

## Answers so far

- **2026-10-16, "Ok":** the human accepted:
  - P1 (the protocol's cache lifetime, read from the previous request);
  - P2 as revised (a default per protocol);
  - the per-file age rule of P5.
- **Before that,** the human asked for a per-file logic. §1 records why the *timing* cannot be
  per file and the *selection* can.
- **2026-10-16, "ignore part B, do not switch anything off, the rest is ok" (translated from Italian):**
  - **P4:** Part A only. **Part B is set aside,** so P5 (outline form) and P7 (E10(f)) are moot.
    The sections on Part B (§0 consequence, P5, §9 Part B, §10) stay as a record. They are not
    in scope.
  - **P6:** nothing is switched off. `edit_args_on_resume` stays as the human configured it.
  - **P3:** a 60 s margin.
- **Spec delta:**
  - `SCR-001-resume-from-cache-ttl.md`;
  - `git diff` of SPEC 001, 003, 009, 017, 019, ADR 0012 (amendment 1) and `TOKLI_ROADMAP.md`
    (the S8i entry).
  - Every changed status line reads "proposed 2026-10-16, pending S8i Gate 1".

Gate 1 record:
- **Date:** 2026-10-16.
- **The human's words:** "the specifications are fine" (translated from Italian), in answer to the request for Gate 1 approval of
  SCR-001 and its delta.
- **Spec delta:** SCR-001 and the `git diff` listed above. The status lines now read
  "approved for S8i 2026-10-16"; ADR 0012 amendment 1 is accepted.
- **After approval,** while deriving tests, Claude found that AC-PR-17's 1 h boundary contradicts
  PR-021 and the 5 min example of the same criterion. `SCR-002-ac-pr-17-boundary.md` proposes the
  fix. **Approved 2026-10-16 ("yes" (translated from Italian))** and applied to SPEC 019.
- **Note:** §5's trace sources (`request`, `fallback`) are superseded by PR-028's
  (`previous_request`, `protocol_default`, `unknown_conversation`); §9's
  `test_resume_after_s_migrated_to_protocol_default` is named `test_renamed_key_resume_after_s`
  (SCR-001 §5).
