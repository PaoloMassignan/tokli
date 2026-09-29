# SPEC 019 — Tool-history pruning

Status: Draft (revised in Phase 0.1) · Slices: S4 (`duplicate_tool_results`, LOSSLESS by reference), S8 (`superseded_tool_results`, SELECTIVE)
Related: SPEC 001 (canonical model), 009 (compression core, preservation model), 010 (catalogue), 012 (evaluation), PHASE0_1_REVIEW.md

## Purpose
Agent conversations resend the whole tool history on every turn. Much of it is repeated or
out of date: the same file read twice, a file read before it was rewritten. Pruning removes that
redundancy at the level of tool calls rather than text. Duplicate results are replaced
**losslessly by reference** (the information stays in the request, provably). Whether the model
uses the reference correctly is a behavioural assumption that is evaluated before the pruner is
enabled by default. Superseded results are removed **selectively**, under LOSSY_ALLOWED.

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
request has byte-identical original text and `tokens(S_j) ≥ pruning.duplicate_min_tokens`
(default 64). S_i is the **earliest** such segment. Stubs always name S_i, never another stub.
With `pruning.duplicate_require_same_call: true`, the two calls must also have the same tool name
and canonically equal arguments. The default is `false`, which is still lossless.

Stub (single line, prefix-stable):
```text
[tokli: identical to the result of tool call <call_id of S_i> earlier in this conversation — <n> tokens omitted]
```
Decoder: `decode(stub) = text of the segment whose call id is named`. The property test decodes the
whole request.

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
available but off, and the result is recorded. It is eligible under LOSSLESS_ONLY either way.

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
| PR-005 | THE pruners SHALL NOT change the number, order or pairing of messages, tool calls, tool results or input items, and SHALL NOT modify tool-call arguments in v1. |
| PR-006 | THE `analyze.tool_resources` analyzer SHALL derive `resource_key` and `action` for each tool record only from `pruning.tool_semantics`. Unknown tools get `action: other` and are never superseded. |
| PR-007 | WHEN a read of resource X is followed later in the same request by a full read or full write of X, AND the superseding record is older than `superseded_min_age_turns` user turns, AND the request-wide saving reaches `superseded_min_saving_tokens`, THE `superseded_tool_results` pruner SHALL stub the earlier read's result. |
| PR-008 | THE `superseded_tool_results` pruner SHALL keep verbatim the latest full read or write of every resource and every result whose resource or action is unknown. |
| PR-009 | THE pruner specs SHALL declare `prefix_stable`, and THE telemetry SHALL record per request whether a non-prefix-stable pruner changed a segment that was already present in the previous turn's position range (`history_rewritten: bool`). |
| PR-010 | THE pruners SHALL run before segment-level compressors (stage `structural`, request scope), so later compressors never spend work on stubbed content. |
| PR-011 | WHEN a stubbed result block carries `cache_control` or `is_error`, THE SYSTEM SHALL preserve those attributes (CM-009, AN-004). |
| PR-012 | THE `duplicate_tool_results` stub SHALL name the earliest byte-identical earlier result, and THE pruner SHALL be subject to reference integrity (CC-019). A later pruner that would stub or otherwise non-equivalently change that earlier result SHALL be rejected for that segment. |
| PR-013 | THE `duplicate_tool_results` pruner SHALL consider TOOL_RESULT segments of tools listed in `verbatim_tools` (CC-021). |
| PR-014 | THE shell-command classification for Codex tools SHALL be exactly the rules in "Shell-command classification" below. A command that matches no rule SHALL get `action: other`. New rules SHALL be added only by a spec change with a test case per rule. |

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
- AC-PR-5 (PR-007): read(F) → edit(F) → read(F) with an age of ≥ 4 turns → the first read is stubbed (SELECTIVE, only under LOSSY_ALLOWED). read(F) → edit(F) with no later read → nothing is stubbed.
- AC-PR-6 (PR-009): a superseding stub on an earlier segment sets `history_rewritten: true`; duplicate stubs never do.
- AC-PR-7: under LOSSLESS_ONLY, `superseded_tool_results` never runs (CC-002).
- AC-PR-8 (PR-012): read(F) → read(F) identical → full read(F) with different content, under LOSSY_ALLOWED with both pruners on: the second read is a duplicate stub naming the first; `superseded_tool_results` is rejected on the first read with `reference_target_modified`; the whole-request decode restores every original text.
- AC-PR-9 (PR-013): a duplicate `Read` result (a tool in `verbatim_tools`) is stubbed.
- AC-PR-10 (PR-014): a table-driven test covers every rule row, each rejection in step 2, and argv vs string forms (bash/PowerShell wrappers, Windows and POSIX paths).

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
`test_duplicate_pruning_applies_to_verbatim_tools` · `test_reference_target_integrity_enforced`

## Open questions
- Q14: How much of the pruning saving measured in E5a (TOKLI_EVIDENCE §2) came from Edit/Write **arguments** rather than results? It needs a per-part count. E5b records tokens by segment kind, including TOOL_CALL_ARGS (read-only).
- Q15 (E10): Do Anthropic and OpenAI accept historical tool calls whose arguments are stubbed (schema-invalid), and does the model behave? If yes, a future `superseded_tool_args` pruner.
- Q16 (E2-ext): What is the cache-invalidation cost of superseding at the chosen age and threshold, against its savings?
