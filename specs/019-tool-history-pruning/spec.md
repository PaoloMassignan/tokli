# SPEC 019 — Tool-history pruning

Status: Draft (revised in Phase 0.1) · Slices: S4 (`duplicate_tool_results`, LOSSLESS by reference), S8 (`superseded_tool_results`, SELECTIVE)
Approved for S4 (2026-10-03): PR-001…PR-005, PR-009 (never set by duplicates), PR-010…PR-013, PR-015. PR-006…PR-008, PR-014 in S8.
Approved for S8c (2026-10-04): `edit_args_on_resume`, PR-005 (as changed), PR-020…PR-026, AC-PR-11…AC-PR-16; ADR 0012.
Approved for S8e (2026-10-04): `reread_by_reference`, PR-030…PR-036, AC-PR-20…AC-PR-26; ADR 0013.
Changed by S6 SCR-001 (approved 2026-10-05): PR-012 (a later change of a target is kept and the stub reverted), AC-PR-8, AC-PR-24.
Changed by S8h SCR-001 (approved 2026-10-09): PR-032 (Claude Code's `Read` numbering), AC-PR-22; `reread_by_reference` version 2, back on by default with its version 2 smoke record (`no_measurable_damage`, 2026-10-09; CC-020).
Related: SPEC 001 (canonical model), 009 (compression core, preservation model), 010 (catalogue), 012 (evaluation), PHASE0_1_REVIEW.md

## Purpose
Agent conversations resend the whole tool history on every turn. Much of it is repeated or
out of date: the same file read twice, a file read before it was rewritten. Pruning removes that
redundancy at the level of tool calls rather than text. Duplicate results are replaced
**losslessly by reference** (the information stays in the request, provably). Whether the model
uses the reference correctly is a behavioural assumption that is evaluated before the pruner is
enabled by default. Superseded results are removed **selectively**, only when the user enables that pruner.

## Rationale
- Agent conversations resend the whole tool history. Repeated and outdated tool results are a large share of it (TOKLI_EVIDENCE §2, E5a, gives an upper reference measured on real traffic).
- Stubbing the *earlier* copy of a duplicate rewrites history that was already sent and breaks provider prefix caching. The *later* copy is stubbed instead.
- Removing whole call/result pairs or merging messages needs protocol-specific atomicity rules (for example Responses reasoning items). v1 avoids them.
- Deciding relevance needs a knowledge model, which Tokli excludes. v1 prunes only exact duplicates (and, selectively, superseded reads).

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 019 rows).

## Terminology
- **Tool record:** a tool call (name, parsed arguments, call id) plus its result segment(s), exposed
  read-only by the adapter (CM-013).
- **Resource key:** an identifier of what a tool call read or wrote (e.g. a normalised file path
  plus range). It is produced by the `analyze.tool_resources` analyzer from **config-driven tool
  semantics**, never by the pruner itself.
- **Stub:** the short text that replaces a pruned tool result's content. The call, the result block
  and the ids stay in place.
- **Reference equivalence:** a transformed request is equivalent to the original if every stub
  names a result that is still present earlier in the same request and has identical content.

## Design decisions

1. **Content-level stubbing, not structural removal (v1).** Pruners replace the *content* of
   `tool_result` / `function_call_output` / `role:"tool"` with a stub. Calls, results, message
   count and order stay intact, so CM-004 still holds and no protocol pairing rule (tool_use ↔
   tool_result, reasoning atomicity, role alternation) can be violated. Removing whole pairs and
   stubbing tool-call **arguments** (e.g. Edit `old_string`/`new_string`) is deferred to
   experiment **E10**.
2. **Keep the earliest duplicate, stub the later ones.** The stub is
   applied to the newest copy when it first appears, so history already sent never changes
   (prefix-stable).
3. **Tool semantics are data.** Which argument of which tool names a resource lives in
   `pruning.tool_semantics` config (defaults for Claude Code and Codex). Pruners see only
   `resource_key` and `action ∈ {read, write, other}`.

## `duplicate_tool_results` — LOSSLESS (equivalence: reference)

Rule: a TOOL_RESULT segment S_j is a duplicate if an earlier TOOL_RESULT segment in the same
request has byte-identical original text (compared on the client's bytes, before any compressor) and `tokens(S_j) ≥ pruning.duplicate_min_tokens`
(default 64). S_i is the **earliest** such segment. Stubs always name S_i, never another stub.
With `pruning.duplicate_require_same_call: true`, the two calls must also have the same tool name
and canonically equal arguments. The default is `false`, which is still lossless.

Stub (single line, prefix-stable):
```text
[tokli: identical to the result of tool call <call_id of S_i> earlier in this conversation — <n> tokens omitted]
```
Decoder: `decode(stub) = text of the segment whose call id is named`. The property test decodes the
whole request.

**Protected spans (S4).** When the replaced text contains protected spans (e.g. `<system-reminder>`
blocks), the stub is the line above followed by each protected span, verbatim and in order, each
on its own line. The decoder ignores them: the target holds the same text.

**Whole results only (S4).** Both the stubbed segment and its target must each be the entire
content of their tool result (a string, or a list holding exactly one text block). Results with
several blocks are never stubbed and never targets.

Claims:

| Claim | Type | Backed by |
|---|---|---|
| Every stubbed text is present, byte-identical, in the earliest earlier copy of the same forwarded request; whole-request decode restores the original | PROVEN | `prop_duplicate_pruning_decodes_whole_request` |
| The target is not altered afterwards except byte- or structurally-equivalently | PROVEN (runtime invariant CC-019) | `test_reference_target_integrity_enforced` |
| Prefix stability; structure, ids and arguments unchanged | PROVEN | `test_duplicate_pruning_prefix_stable_across_turns`, `test_pruning_preserves_structure_and_arguments` |
| The model answers about the later call from the earlier content (`resolves_result_reference`) | ASSUMPTION | smoke evaluation (SPEC 012, QE-012…QE-016), E11 |
| The agent quotes stubbed content correctly from the earlier copy (`quotes_from_reference_target`) | ASSUMPTION | smoke evaluation, E11; Tier 3 before v1 release |
| `duplicate_min_tokens` = 64 | POLICY (provisional) | S4 data |

It is **exempt from `verbatim_tools`** (CC-021): the verbatim bytes remain in the target. That
exemption is exactly what the assumption `quotes_from_reference_target` covers.

**Default enablement (POLICY).** `default_enabled: true` only if the smoke evaluation record for
both assumptions has verdict `no_measurable_damage` at the end of S4 (CC-020). Otherwise it ships
available but off, and the result is recorded. The "Lossless only" shortcut keeps it on either way.

## `superseded_tool_results` — SELECTIVE (S8)

Rule: a TOOL_RESULT of a `read` of resource X is superseded if a **later** tool record in the same
request performs a *full* `read` of X or a *full* `write` of X whose content is in its arguments
(e.g. `Write`). Partial reads (offset/limit, `head`) have range-qualified keys and supersede only an
identical range. An `Edit` never supersedes, because the earlier read is needed to know the current
state. Guarantee: the latest full view of every resource stays verbatim.

Stub:
```text
[tokli: outdated contents of <resource display name> omitted — a newer full read/write appears later (call <call_id>)]
```

This rule depends on **later** records, so it rewrites history that has already been sent. It is
declared `prefix_stable: false`. Every newly superseded read invalidates the provider cache from
that point. Mitigation (to be validated by E2-ext): apply superseding only to results older than
the last `pruning.superseded_min_age_turns` (default 4) user turns, and only when the request-wide
saving is at least `pruning.superseded_min_saving_tokens` (default 8,000).

## Requirements

| ID | EARS requirement |
|---|---|
| PR-001 | THE SYSTEM SHALL implement pruners as compressors (SPEC 009) with request scope. They receive all mutable TOOL_RESULT segments and the read-only tool records, and they return patches only. |
| PR-002 | WHEN a TOOL_RESULT segment has byte-identical text to an earlier TOOL_RESULT segment in the same request and meets the minimum size, THE `duplicate_tool_results` pruner SHALL replace the later segment's text with a stub naming the earlier call id. |
| PR-003 | THE `duplicate_tool_results` pruner SHALL never stub the earliest occurrence, SHALL never reference a segment that is not present earlier in the same request, and SHALL decode (whole request) to the original texts. |
| PR-004 | THE patch produced by `duplicate_tool_results` for segment j SHALL depend only on segments 0…j (prefix stability). |
| PR-005 | THE pruners SHALL NOT change the number, order or pairing of messages, tool calls, tool results or input items, and SHALL NOT modify tool-call arguments in v1, except the argument strings that `edit_args_on_resume` replaces under PR-022 (S8c). |
| PR-006 | THE `analyze.tool_resources` analyzer SHALL derive `resource_key` and `action` for each tool record only from `pruning.tool_semantics`. Unknown tools get `action: other` and are never superseded. |
| PR-007 | WHEN a read of resource X is followed later in the same request by a full read or full write of X, AND the superseding record is older than `superseded_min_age_turns` user turns, AND the request-wide saving reaches `superseded_min_saving_tokens`, THE `superseded_tool_results` pruner SHALL stub the earlier read's result. |
| PR-008 | THE `superseded_tool_results` pruner SHALL keep verbatim the latest full read or write of every resource and every result whose resource or action is unknown. |
| PR-009 | THE pruner specs SHALL declare `prefix_stable`, and THE telemetry SHALL record per request whether a non-prefix-stable pruner changed a segment that was already present in the previous turn's position range (`history_rewritten: bool`). |
| PR-010 | THE pruners SHALL run before segment-level compressors (stage `structural`, request scope), so later compressors never spend work on stubbed content. |
| PR-011 | WHEN a stubbed result block carries `cache_control` or `is_error`, THE SYSTEM SHALL preserve those attributes (CM-009, AN-004). |
| PR-012 | THE `duplicate_tool_results` stub SHALL name the earliest byte-identical earlier result, and THE pruner SHALL be subject to reference integrity (CC-019). A transformation of that earlier result by a later pruner or compressor SHALL be kept, and the stub SHALL be reverted (CC-019). (S6 SCR-001.) |
| PR-013 | THE `duplicate_tool_results` pruner SHALL consider TOOL_RESULT segments of tools listed in `verbatim_tools` (CC-021). |
| PR-015 | THE `duplicate_tool_results` stub SHALL keep every protected span of the replaced text, verbatim and in order, after the stub line, AND the pruner SHALL consider only tool results whose whole content is one text segment, as stub and as target. `reference_stubs` (TC-014) SHALL count the accepted stubs of the forwarded request. (S4 review P6, P7, A5.) |
| PR-014 | THE shell-command classification for Codex tools SHALL be exactly the rules in "Shell-command classification" below. A command that matches no rule SHALL get `action: other`. New rules SHALL be added only by a spec change with a test case per rule. |
| PR-030 | THE `reread_by_reference` pruner SHALL be LOSSLESS with equivalence `reference`, request scope, `prefix_stable: true`, and SHALL be off by default until a smoke record allows its default (CC-020). |
| PR-031 | WHEN a result of a tool in `pruning.reread_tools` names a file path for which an earlier record of the same request holds original text (a whole result of a re-read tool, or the `content` of a `Write`), THE pruner SHALL take the latest such record as source and SHALL replace each run of at least `pruning.reread_min_run_lines` consecutive numbered lines whose contents equal, in order, consecutive source lines with one note in the exact format of this section, keeping every other line verbatim and in place. |
| PR-032 | THE pruner SHALL apply only to results whose numbered lines all carry the same numbering style with consecutive numbers: either `"{n:>6}\t"` (`cat -n`) or `"{n}\t"` (Claude Code's `Read`). Otherwise it SHALL report `not_applicable(nonstandard_numbering)`. The lines it keeps and the lines that decoding rebuilds SHALL use the result's own style. WHEN the style cannot be recovered from the replaced result and its source alone, THE pruner SHALL NOT replace it, and SHALL report `not_applicable(ambiguous_numbering)`. Without a source it SHALL report `not_applicable(no_source)`, and without a qualifying run `not_applicable(no_run)`. (S8h SCR-001.) |
| PR-033 | THE pruner SHALL NOT use as source a text that a reference pruner changed, so that notes never point to notes. |
| PR-034 | THE pruner's decode SHALL rebuild the original result byte for byte from the notes and the source, AND every source SHALL be a reference target under CC-019. |
| PR-035 | THE pruner SHALL NOT consider a result or a source with more than `pruning.reread_max_lines` lines, and its time SHALL grow at most linearly with the lines of a typical re-read (a run-dominated alignment). |
| PR-036 | THE `reread_by_reference` pruner SHALL keep every protected span of the result verbatim and in order, and SHALL be exempt from `verbatim_tools` under CC-021. |
| PR-020 | THE `edit_args_on_resume` pruner SHALL be SELECTIVE, request scope, `prefix_stable: false`, off by default, and SHALL run only when enabled (CC-002). |
| PR-021 | WHEN a request's conversation (key per ADR 0012) was last seen more than `pruning.resume_after_s` seconds ago, or is not known to Tokli, THE SYSTEM SHALL treat the request as a resume; otherwise it SHALL NOT. |
| PR-022 | AT a resume, THE `edit_args_on_resume` pruner SHALL replace with the stub every argument string listed in `pruning.resume_edit_fields` for its tool, of at least `pruning.resume_min_tokens` tokens, in every tool call followed by at least `pruning.resume_min_age_turns` human turns, and SHALL keep every other key and value, the call id and the block order. |
| PR-023 | BETWEEN two resumes of a conversation, THE pruner SHALL apply exactly the replacements decided at its last resume to the calls still present, and no others, so that the forwarded prefix is byte-identical from one request to the next. |
| PR-024 | THE conversation store SHALL keep, per conversation key, only the time of the last request and the pruned call ids; it SHALL be bounded by `pruning.conversation_states` with least-recently-used eviction, and SHALL NOT be written to disk. |
| PR-025 | WHEN a resume changes an argument string, THE SYSTEM SHALL record `history_rewritten: true` (PR-009); THE per-compressor statistics SHALL count each replaced string as one accepted segment. |
| PR-026 | THE pruners SHALL count human turns as defined in this spec (a user message holding human text); messages that carry only tool results SHALL NOT count. |

## `edit_args_on_resume` — SELECTIVE (S8c)

Rationale: TOKLI_EVIDENCE §2 (E5b-lite).
- Most of the cost of agent traffic is the provider cache.
- Three quarters of the cache writes follow a pause of more than an hour, when the whole context
  is written again.
- The contents written by `Write` and the strings of `Edit` are about a third of the resent
  content.

Pruning them only at those moments avoids an extra cache rewrite. Keeping the pruning
afterwards keeps the cache valid.

**Conversation state** (ADR 0012).
- **Key:** SHA-256 of the canonical JSON of `system` and the first message.
- **What Tokli keeps per key:** the wall-clock time of the conversation's last request, and the
  set of tool-call ids pruned at its last resume.
- **Where:** in memory only, bounded by `pruning.conversation_states` (least recently used).

**Resume.** A request is a resume when its conversation was last seen more than
`pruning.resume_after_s` ago (default 3,600), or is not known (S8c review P5).

**Human turn.** A user message that holds human text (a string, or a text block in a message
without `tool_result` blocks). Messages that carry only tool results are not human turns.

**Stub** (replaces each pruned argument string):
```text
[tokli: earlier edit content omitted (<n> tokens) — read the file for its current state]
```

Claims:

| Claim | Type | Backed by |
|---|---|---|
| Keys, `file_path`, ids, order and structure are unchanged; only listed argument strings change | PROVEN | `test_resume_pruning_keeps_structure_and_paths` |
| Between two resumes the forwarded prefix is byte-identical | PROVEN | `test_resume_pruning_stable_between_resumes` |
| Only calls older than `resume_min_age_turns` human turns are pruned, and only at a resume | PROVEN | `test_resume_pruning_only_at_resume_and_old_calls` |
| The agent does not need, hours later, the exact text it wrote, and re-reads the file when it does (`edit_content_not_needed`) | ASSUMPTION | smoke family `reread_after_pruned_edit` (SPEC 012) |
| The provider accepts a history whose edit arguments were changed | ASSUMPTION | E10(a), before code |

## `reread_by_reference` — LOSSLESS (equivalence: reference, S8e)

Rationale: TOKLI_EVIDENCE §2 (repeated reads; E10(e)).
- In the developer's sessions, 12.7 % of the `Read` volume can be rebuilt exactly from the
  request: the last read with the agent's edits applied, or the agent's own `Write`.
- A re-read that sends only its changed lines and refers to the earlier text for the unchanged
  runs kept every edit anchor exact, with no refusal (E10(e)).

**Rule (ADR 0013).** For a result of a tool in `pruning.reread_tools` (default `Read`) that names
a file path, the **source** is the latest earlier record of the same normalised path in the same
request whose text is still original:
- a whole result of a re-read tool;
- the `content` argument of a `Write`.

Each run of at least `pruning.reread_min_run_lines` (default 5) consecutive numbered lines whose
contents equal, in order, consecutive lines of the source is replaced by one note. Every other
line stays verbatim in place, including `<system-reminder>` blocks.

**Note** (one line per replaced run):
```text
[tokli: lines <a>-<b> unchanged — identical to lines <c>-<d> of the read in call <id>]
```
For a `Write` source: `… identical to lines <c>-<d> of the content written in call <id>]`.

**Decode:** each note is replaced by the source's lines `c`-`d`, renumbered `a`-`b` with the
`"{n:>6}\t"` prefix. The whole-request decode restores every original text.

Claims:

| Claim | Type | Backed by |
|---|---|---|
| Whole-request decode restores every original result byte for byte | PROVEN | `prop_reread_by_reference_decodes_whole_request` |
| Sources precede the result, are original, and stay intact (CC-019) | PROVEN | `test_reread_source_integrity_enforced` |
| Prefix stability; structure unchanged | PROVEN | `test_reread_prefix_stable_across_turns` |
| The model reads the current file from the changed lines plus the referenced earlier lines (`reads_partial_reference`) | ASSUMPTION | smoke family `reread_fact_lookup` |
| The agent copies edit anchors for unchanged lines exactly from the referenced earlier text (`quotes_from_reference_target`) | ASSUMPTION | smoke family `reread_edit_anchor` (E10(e): 20/20) |

## Default tool semantics (config data, revisable)

| Client | Tool | Resource argument | Action |
|---|---|---|---|
| Claude Code | `Read` | `file_path` (+ `offset`,`limit` → range) | read |
| Claude Code | `Write` | `file_path` | write (full, content in args) |
| Claude Code | `Edit`, `MultiEdit`, `NotebookEdit` | `file_path` / `notebook_path` | write (partial, never supersedes) |
| Codex | `shell` / `shell_command` / `container.exec` / `exec` | classified by the shell-command rules below | read / write / other |

### Shell-command classification (Codex tools)

1. **Script extraction.** If the command is an argv list whose first element's basename (without
   `.exe`, case-insensitive) is `bash`, `sh`, `zsh`, `pwsh` or `powershell`, and whose last element
   is a string, the script is that last element. A plain command string is the script itself. Any
   other argv list is classified from its elements directly (element 0 = program).
2. **Simple commands only.** A script containing, outside quotes, any of `|`, `;`, `&`, `>`, `<`,
   `` ` ``, `$(` or a newline is `other`. Otherwise it is split into words on whitespace,
   honouring single and double quotes.
3. **Rules** (program name matched case-insensitively; exactly one path operand unless stated):

| Program and form | Action | Resource key |
|---|---|---|
| `cat <path>` (no options) · `type <path>` | read, full | `<path>` |
| `Get-Content <path>` or `Get-Content -Path <path>` | read, full | `<path>` |
| `Get-Content … -TotalCount N` / `-Head N` · `head -n N <path>` / `head -N <path>` / `head <path>` (N = 10) | read, range `head:N` | `<path>` + range |
| `Get-Content … -Tail N` · `tail -n N <path>` / `tail -N <path>` / `tail <path>` (N = 10) | read, range `tail:N` | `<path>` + range |
| `apply_patch` (patch in the script or the next argument) | write, **partial** (never supersedes) | every path named in `*** Add File:`, `*** Update File:`, `*** Delete File:` lines |
| `Set-Content <path> …` · `Out-File <path> …` | write, **partial** (content not reliably in arguments; never supersedes) | `<path>` |
| anything else, any unknown option, or more than one path operand | other | — |

**Path normalisation** (all tools, no filesystem access): replace `\` with `/`; collapse repeated
`/`; remove `./` segments; lowercase a leading drive letter; strip surrounding quotes. Relative
and absolute spellings of the same file stay **different** keys, which errs on the side of not
superseding.

## Acceptance criteria
- AC-PR-1 (PR-002/003): a fixture where the same file is read 3 times unchanged → the 2nd and 3rd results are stubs naming the 1st call id. The whole-request decode equals the original. Structure is unchanged.
- AC-PR-2 (PR-004): turn N and turn N+1 bodies (N+1 = N + new duplicate read) → the shared prefix is byte-identical after pruning.
- AC-PR-3 (PR-005): for all compat fixtures with pruning on, block/item counts, ids and argument JSON are unchanged.
- AC-PR-4 (PR-006/008): an unknown tool with a `file_path` argument is never superseded. The latest full read of every file is verbatim.
- AC-PR-5 (PR-007): read(F) → edit(F) → read(F) with an age of ≥ 4 turns → the first read is stubbed (SELECTIVE, only when enabled). read(F) → edit(F) with no later read → nothing is stubbed.
- AC-PR-6 (PR-009): a superseding stub on an earlier segment sets `history_rewritten: true`; duplicate stubs never do.
- AC-PR-7: `superseded_tool_results` runs only when enabled, is never enabled by default, and the "Lossless only" shortcut switches it off (CC-002).
- AC-PR-8 (PR-012): read(F) → read(F) identical → full read(F) with different content, with both pruners on: `superseded_tool_results` stubs the first read and the duplicate stub on the second read is reverted with `reference_target_changed` (CC-019 after S6 SCR-001); the whole-request decode restores every original text.
- AC-PR-9 (PR-013): a duplicate `Read` result (a tool in `verbatim_tools`) is stubbed.
- AC-PR-10 (PR-014): a table-driven test covers every rule row, each rejection in step 2, and argv vs string forms (bash/PowerShell wrappers, Windows and POSIX paths).
- AC-PR-20 (PR-031): read(F) → edit one line of F → read(F): the second read keeps the changed lines and becomes two notes with the right line ranges (the ranges shift after an inserted line); the whole-request decode equals the original.
- AC-PR-21 (PR-031): write(F, text) → read(F) unchanged except one line: the notes name the `Write` call ("content written").
- AC-PR-22 (PR-032): a result with another numbering, or no earlier record of F, is not changed, with the stated reason. A result numbered `"{n}\t"` (Claude Code), re-read after an edit, is replaced by notes and decodes byte for byte; a result mixing the two styles is not changed (`nonstandard_numbering`). (S8h SCR-001.)
- AC-PR-23 (PR-033): read1(F) → read2(F) referenced → read3(F): the notes of read3 name read1, never read2.
- AC-PR-24 (PR-034, CC-019): a later compressor that changes a source is kept, and the notes that name the source are reverted with `reference_target_changed`; no note names a changed source. (S6 SCR-001.)
- AC-PR-25 (PR-036): a `<system-reminder>` appended to the re-read stays verbatim; `Read` (a verbatim tool) is handled.
- AC-PR-26 (PR-035): the alignment of a 5,000-line and a 50,000-line re-read with one changed line keeps a time ratio of at most 15 (best of 3), and results over `reread_max_lines` are skipped.
- AC-PR-11 (PR-021, PR-022): a conversation with a `Write` and an `Edit` at turn 1 and six more human turns; with a clock two hours after the previous request → `content`, `old_string` and `new_string` are stubbed, `file_path`, ids and structure are unchanged. One hour minus a second → nothing changes.
- AC-PR-12 (PR-023): after a resume, a request one minute later with one more turn → the forwarded body before the new turn is byte-identical to the previous forwarded body, and no newly old call is pruned.
- AC-PR-13 (PR-021): an unknown conversation is a resume (S8c review P5).
- AC-PR-14 (PR-020): off by default; the "Lossless only" shortcut switches it off.
- AC-PR-15 (PR-024): the store never exceeds its bound, and no file is written.
- AC-PR-16 (PR-022, PR-026): a call followed by three human turns and many tool-only messages is not pruned; strings under `resume_min_tokens` are not pruned.

## Test scenarios
`test_duplicate_results_stub_later_copies` · `prop_duplicate_pruning_decodes_whole_request` ·
`test_duplicate_pruning_never_stubs_first_occurrence` · `test_duplicate_pruning_prefix_stable_across_turns` ·
`test_duplicate_require_same_call_option` · `test_pruning_preserves_structure_and_arguments` ·
`test_tool_semantics_from_config_only` · `test_unknown_tool_never_superseded` ·
`test_superseded_read_stubbed_after_full_reread` · `test_edit_never_supersedes` · `test_partial_read_ranges` ·
`test_superseded_respects_age_and_min_saving` · `test_history_rewritten_flag` ·
`test_pruning_runs_before_segment_compressors` · `test_stub_preserves_cache_control_and_is_error` ·
`test_lossless_only_never_runs_lossy_compressor` (with pruners registered) ·
`test_shell_command_classification_rules` · `test_path_normalisation` ·
`test_duplicate_stub_names_earliest_copy` · `test_superseded_rejected_on_reference_target` ·
`test_duplicate_pruning_applies_to_verbatim_tools` · `test_reference_target_integrity_enforced` ·
`test_duplicate_stub_keeps_protected_spans` · `test_multi_block_results_not_pruned` · `test_reference_stubs_counted` ·
`test_resume_pruning_keeps_structure_and_paths` · `test_resume_pruning_stable_between_resumes` ·
`test_resume_pruning_only_at_resume_and_old_calls` · `test_unknown_conversation_is_resume` ·
`test_conversation_store_bounded_and_memory_only` · `test_human_turn_definition` · `test_resume_pruning_off_by_default` ·
`prop_reread_by_reference_decodes_whole_request` · `test_reread_notes_after_edit` · `test_reread_source_write` ·
`test_reread_not_applicable_reasons` · `test_reread_never_chains_notes` · `test_reread_source_integrity_enforced` ·
`test_reread_keeps_reminders_and_verbatim_tool` · `test_reread_linear_time` · `test_reread_prefix_stable_across_turns`

## Open questions
- Q14: How much of the pruning saving measured in E5a (TOKLI_EVIDENCE §2) came from Edit/Write **arguments** rather than results? It needs a per-part count. E5b records tokens by segment kind, including TOOL_CALL_ARGS (read-only).
- Q15 (E10): Do Anthropic and OpenAI accept historical tool calls whose arguments are stubbed (schema-invalid), and does the model behave? If yes, a future `superseded_tool_args` pruner.
- Q16 (E2-ext): What is the cache-invalidation cost of superseding at the chosen age and threshold, against its savings?
