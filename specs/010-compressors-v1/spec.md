# SPEC 010 — v1 compressor catalogue

Status: Draft (revised in Phase 0.1) · Slices: S1 (`json_minify`), S4 (`duplicate_tool_results`, SPEC 019), S8 (`search_group`, `dictionary`, `diff_context_trim`, `log_filter`, `superseded_tool_results`)
Approved for S4 (2026-10-03): the `duplicate_tool_results` entry and its assumptions.
Approved for S1 (2026-09-30): CP-JM-001…CP-JM-005.
Changed by SCR-001 (2026-10-02): `test_json_minify_linear_time` measurement sizes.
Approved for S8a-1 (2026-10-03): `search_group` (CP-SG-001…004) and `log_filter` (CP-LF-001…004) with the
options, reason codes and clarifications of S8a review A6 and A8, and `apply_to_verbatim_tools` (S8a SCR-001).
Changed by S8a SCR-003 (2026-10-04): the grep-line definition (no whitespace; a `/`, `\` or `.` in the path).
Related: SPEC 009 (contract, preservation model, claim types), SPEC 012 (evaluation), PHASE0_1_REVIEW.md

Every compressor here is a registry entry satisfying SPEC 009. Common engine-level rules
(policy, min tokens, `verbatim_tools`, acceptance gate, protected spans, reference integrity) are
**not** repeated. Claim labels (PROVEN, ASSUMPTION, HEURISTIC, POLICY) are defined in SPEC 009.

## Summary

| id | kind | equivalence | scope | prefix-stable | Tokli notation in output | "Lossless only" shortcut | default enabled (POLICY) | slice |
|---|---|---|---|---|---|---|---|---|
| `json_minify` | LOSSLESS | structural | segment | yes | none (standard JSON) | kept on | **yes, provisional** until its S2.5 smoke-evaluation record exists (QE-016) | S1 |
| `duplicate_tool_results` | LOSSLESS | reference | request | yes | reference stub | kept on | **yes**: smoke record `no_measurable_damage` on `claude-opus-5-5` (E11, 2026-10-03; CC-020) | S4 |
| `search_group` | LOSSLESS | byte | segment | yes | `[file]` headers, `\` escapes | kept on | no (until an evaluation record exists; E8) | S8a-1 |
| `dictionary` | LOSSLESS | byte | segment | yes | `§X` symbols + legend | kept on | no (until E7/E8) | S8a-2 |
| `superseded_tool_results` | SELECTIVE | none | request | **no** | supersession stub | switched off | no | S8a-3 |
| `diff_context_trim` | SELECTIVE | none | segment | yes | omission note | switched off | no | S8a-2 |
| `log_filter` | SELECTIVE | none | segment | yes | omission note | switched off | no | S8a-1 |
| `reread_by_reference` | LOSSLESS | reference | request | yes | line-range notes | kept on | **yes**: smoke record `no_measurable_damage` on `claude-opus-5-5` (2026-10-04; CC-020) | S8e (SPEC 019) |
| `edit_args_on_resume` | SELECTIVE | none | request | **no** (prunes only when the cache is rewritten anyway) | edit-omitted stub | switched off | no | S8c (SPEC 019) |

### Assumption ids (behavioural; each is an evaluation case family in SPEC 012)

| Assumption id | Statement | Declared by |
|---|---|---|
| `not_quoted_verbatim` | The agent never needs to reproduce the transformed tool result byte-exactly (e.g. as an edit anchor). The `verbatim_tools` list (HEURISTIC) excludes the tools for which this is known to be false. | every text-changing compressor except `duplicate_tool_results` |
| `reads_minified_json` | The model extracts the same facts from minified JSON as from the pretty-printed original. | `json_minify` |
| `resolves_result_reference` | Given a stub naming an earlier tool call, the model answers questions about the later call from the earlier call's content. | `duplicate_tool_results` |
| `quotes_from_reference_target` | When the agent must reproduce stubbed content byte-exactly, it copies it correctly from the referenced earlier copy. | `duplicate_tool_results` (CC-021) |
| `reads_grouped_search` | The model attributes every grouped match to the correct path and line number. | `search_group` |
| `applies_dictionary_legend` | The model expands `§X` symbols correctly when reasoning about or quoting the text. | `dictionary` (E7) |
| `outdated_content_not_needed` | Once a newer full view of a resource exists, the model does not need the older one. | `superseded_tool_results` |
| `context_lines_not_needed` | Unchanged diff context beyond `max_context` lines is not needed, and the diff is not applied mechanically from the transformed text (hunk line counts no longer match). | `diff_context_trim` |
| `omitted_log_lines_not_needed` | Repeated INFO/NOTICE lines beyond the first per pattern, and unsampled DEBUG/TRACE lines, are not needed for the task. | `log_filter` |
| `reads_partial_reference` | The model reads a re-read file as its changed lines plus the earlier lines that the notes name. | `reread_by_reference` (S8e) |
| `edit_content_not_needed` | Hours after writing or editing a file, the agent does not need the exact text it wrote; when it needs the file it reads it again. | `edit_args_on_resume` (S8c) |

Default `compression.verbatim_tools` (HEURISTIC, config data): `["Read", "Bash", "shell",
"shell_command", "container.exec"]`. These are tool results that agents are likely to quote back
verbatim (file contents, command output reused in edits). E8 revises the list. A compressor that
declares the option `apply_to_verbatim_tools` can be applied to these tools too, when the user
sets the option (default false; CC-021 after S8a SCR-001). In S8a-1 `search_group` and
`log_filter` declare it.

---

## `json_minify` (S1)

**Problem.** Pretty-printed JSON in tool results (MCP tools, API responses, `gh api`) spends
tokens on indentation and newlines.

**Algorithm.**
1. Applicability: trimmed text starts with `{` or `[`, AND the whole trimmed text parses as strict
   JSON (RFC 8259: no NaN/Infinity, no trailing garbage), AND the text contains at least one
   whitespace character outside strings.
2. Lexical minification: copy the text character by character. Outside string literals, drop
   JSON whitespace (`U+0020`, `\t`, `\n`, `\r`). Inside string literals, copy verbatim,
   honouring `\` escapes. Leading and trailing whitespace of the segment is dropped.
3. **No parse-and-dump.** Number spelling (`1.0`, `1e2`), escape sequences (`\u00e9`), key order and
   duplicate keys are preserved exactly.

**Decoder / equivalence.** `decode(x) = x`. Equivalence is structural: `P(original) == P(output)`,
where `P` = `json.loads` with `object_pairs_hook=list`, `parse_float=str`, `parse_int=str`,
`parse_constant=reject`.

**Claims.** PROVEN: structural equivalence under `P`; O(n) time and memory. ASSUMPTION:
`reads_minified_json`, `not_quoted_verbatim`. HEURISTIC: `verbatim_tools`.

| ID | EARS requirement |
|---|---|
| CP-JM-001 | WHEN a TOOL_RESULT or USER_TEXT segment consists solely of a strict JSON value containing insignificant whitespace, THE `json_minify` compressor SHALL return the value with all insignificant whitespace removed. |
| CP-JM-002 | THE `json_minify` compressor SHALL preserve string contents, escape sequences, number spellings, key order and duplicate keys byte-for-byte. |
| CP-JM-003 | WHEN the segment is not solely strict JSON, THE compressor SHALL report `not_applicable(not_json)`. |
| CP-JM-004 | (engine rule, restated for traceability) WHEN the segment's tool is in `verbatim_tools`, THE engine SHALL skip `json_minify` with reason `verbatim_tool`. |
| CP-JM-005 | THE compressor SHALL run in O(n) time and SHALL NOT allocate more than O(n) additional memory. |

Tests: `prop_json_minify_decode_roundtrip` (Hypothesis JSON generator with random whitespace and
unicode, duplicate keys, exotic numbers) · `test_json_minify_preserves_number_spelling` ·
`test_json_minify_preserves_duplicate_keys` · `test_json_minify_not_applicable_on_mixed_text` ·
`test_json_minify_rejects_nan` · `test_json_minify_crlf_roundtrip` · `test_json_minify_skipped_for_verbatim_tool` ·
`test_json_minify_linear_time` (complexity check: for inputs of 5 MB and 50 MB, best of 3 runs each, the time ratio stays ≤ 15; SCR-001).

Expected saving: unknown on real traffic until E5b. It is measured per release on the golden
corpus (Tier 1).

---

## `duplicate_tool_results` (S4)

Normative text: SPEC 019. **Claims.** PROVEN: whole-request decode, reference integrity (CC-019),
prefix stability, unchanged structure and arguments. ASSUMPTION: `resolves_result_reference`,
`quotes_from_reference_target`. Exempt from `verbatim_tools` (CC-021).

---

## `search_group` (S8a-1)

**Problem.** grep/ripgrep output repeats the file path on every match line.

**Grep line.** A line of the form `<path>:<line>:<content>`, where `<line>` is one or more ASCII
digits and `<path>` is a POSIX path, a Windows drive-letter path (`C:\…`, `C:/…`) or a UNC path
(`\\server\share\…`) that contains no `:` other than the drive-letter colon, no whitespace, and at
least one `/`, `\` or `.` (S8a SCR-003: log timestamps such as `2026-10-03 09:00:01` are not paths).

**Format (v1).** Consecutive runs (≥ 2 lines) with the same path become:
```text
[file] <path>
  <line>:<content>
  <line>:<content>
```
All other lines, including `--` separators, headers and prose, stay **in place, verbatim**.
Escaping: an original line that starts with `[file] `, `\`, or two spaces followed by `digits:`
is emitted with a leading `\`. Decoding reverses this exactly. Line endings are preserved per line
(split with `keepends=True`).

**Options (S8a-1).**
- `compressors.search_group.min_group_lines` (default 5): the segment must contain at least this
  many grep lines **in total**, not per group (S8a review A8). A group still needs ≥ 2
  consecutive lines with the same path.
- `compressors.search_group.apply_to_verbatim_tools` (default false).

**Reason codes:** `not_applicable(too_few_grep_lines)`; `not_applicable(no_group)`, when no
run of ≥ 2 consecutive same-path lines exists.

**Claims.** PROVEN: byte round-trip; unparsed lines stay in place. ASSUMPTION:
`reads_grouped_search`, `not_quoted_verbatim`.

| ID | EARS requirement |
|---|---|
| CP-SG-001 | WHEN a segment contains at least `min_group_lines` (default 5) grep lines, THE `search_group` compressor SHALL group consecutive same-path lines under a `[file]` header. |
| CP-SG-002 | THE compressor SHALL keep every line that is not a grep line in its original position and content (escaped if needed). |
| CP-SG-003 | THE compressor SHALL recognise POSIX, Windows drive-letter and UNC paths. |
| CP-SG-004 | `decode(compress(x)) == x` byte-for-byte, including CRLF, LF and mixed line endings. |

Tests: `prop_search_group_decode_roundtrip` · `test_search_group_windows_paths_roundtrip` ·
`test_search_group_keeps_unparsed_lines_in_place` · `test_search_group_escaping` · `test_search_group_crlf_roundtrip`.

---

## `dictionary` (S8a-2)

**Problem.** Long phrases repeated many times inside one segment.

**Candidates.** A phrase is a run of at least `min_phrase_words` (default 3) whitespace-separated
words within **one line**, at least `min_phrase_chars` (default 20) characters long, containing
**no digit**, and lying entirely outside excluded regions. Excluded regions are protected spans,
URLs (`<scheme>://` up to the next whitespace), and quoted strings (text between matching `"`,
`'` or `` ` `` on one line). A candidate must occur at least `min_occurrences` (default 3) times,
counted without overlap.

**Selection (deterministic).** Repeatedly choose the candidate with the highest net gain
`occurrences × tokens(phrase) − occurrences × tokens(symbol) − tokens(legend line)`. Break ties by
longer phrase first, then by lexicographic order. Replace all its non-overlapping occurrences from
left to right. Stop when no candidate has a net gain ≥ 1, or after `max_entries` (default 26)
entries. Later candidates are searched in the already-substituted text.

**Output.** Symbols are `§A` … `§Z` in assignment order:
```text
[tokli:dict]
§A=<phrase>
§B=<phrase>
[tokli:text]
<substituted text>
```
Legend and markers use `\n`. The substituted text keeps its original line endings. The legend stays
**inside the segment**, so compression remains context-free (CC-006).

**Collision guard.** Not applicable if the input contains `§` followed by an ASCII uppercase
letter, or the literal `[tokli:dict]` or `[tokli:text]`.

**Decoder.** If the text starts with `[tokli:dict]\n`, parse `§X=<phrase>` lines up to
`[tokli:text]\n`. Take the remainder as the body and replace the symbols in **reverse** assignment
order (the last assigned first), so that phrases containing earlier symbols expand correctly.
Any other text decodes to itself.

**Claims.** PROVEN: byte round-trip; no substitution inside excluded regions. ASSUMPTION:
`applies_dictionary_legend` (E7), `not_quoted_verbatim`.

| ID | EARS requirement |
|---|---|
| CP-DI-001 | THE `dictionary` compressor SHALL substitute only candidates as defined above, selected deterministically, with net token gain including legend cost. |
| CP-DI-002 | THE compressor SHALL be not applicable when collision markers exist in the input. |
| CP-DI-003 | `decode(compress(x)) == x` byte-for-byte. |
| CP-DI-004 | THE compressor SHALL NOT substitute inside protected spans, URLs, quoted strings, or any phrase containing a digit. |

Tests: `prop_dictionary_decode_roundtrip` · `test_dictionary_collision_guard` ·
`test_dictionary_does_not_touch_urls_or_protected_spans` · `test_dictionary_selection_deterministic_tie_break` ·
`test_dictionary_nested_symbol_decode_order` · `test_dictionary_no_gain_not_applied`.

---

## `diff_context_trim` (S8a-2, SELECTIVE)

**Applicability.** Only when the `diff_shape` feature (SPEC 011) holds.

Guarantees (each a named test): every `diff --git`, `index`, `---`, `+++` and `@@` header line
is kept verbatim · every `+`/`-` line is kept verbatim · at most `max_context` (default 1)
unchanged lines are kept around each change cluster · text after the last hunk that is not a
valid hunk line is kept verbatim · a note `[tokli: N context lines omitted]` is appended when N > 0.
Hunk headers are **not** rewritten, so their line counts no longer match the body. The output is
not an applicable patch (assumption `context_lines_not_needed`).

**Claims.** PROVEN: the guarantees above. ASSUMPTION: `context_lines_not_needed`,
`not_quoted_verbatim`. HEURISTIC: `diff_shape` detection.

| ID | EARS requirement |
|---|---|
| CP-DT-001 | THE `diff_context_trim` compressor SHALL preserve all header lines and all changed lines verbatim. |
| CP-DT-002 | THE compressor SHALL pass through verbatim any line after a hunk that is not a valid unified-diff hunk line. |
| CP-DT-003 | WHEN lines are omitted, THE compressor SHALL append an omission note stating the count. |
| CP-DT-004 | WHEN the segment does not have `diff_shape`, THE compressor SHALL report `not_applicable(not_diff)`. |

Tests: `test_diff_trim_preserves_changed_lines` · `test_diff_trim_preserves_headers` ·
`test_diff_trim_does_not_swallow_trailing_text` · `test_diff_trim_omission_note` ·
`test_diff_trim_false_positive_shapes` (Markdown bullet lists, YAML lists, `+`/`-` arithmetic in
prose, a lone `@@` in text: all `not_applicable`).

---

## `log_filter` (S8a-1, SELECTIVE)

**Level keywords.** Whole-word, case-insensitive matches of `FATAL`, `CRITICAL`, `ERROR`,
`EXCEPTION`, `WARN`, `WARNING` (severe class) and `INFO`, `NOTICE`, `DEBUG`, `TRACE` (routine
class). A line with **any** severe-class keyword is severe, even if it also contains a routine
keyword. A line with only routine-class keywords takes the most verbose one present, in the order
TRACE > DEBUG > NOTICE > INFO (TRACE if present, then DEBUG, and so on). A line with no keyword is
unleveled.

**Pattern normalisation.** Replace every maximal run of ASCII digits with `#`, and every maximal
run of ≥ 8 hexadecimal characters that contains a digit with `#`. Compare the results exactly.

Guarantees: severe and unleveled lines kept verbatim · for each normalised INFO/NOTICE pattern,
the first occurrence kept · for each normalised DEBUG/TRACE pattern, occurrences 1, 1+k, 1+2k, …
kept, with k = `debug_sample` (default 10) · applicable only if ≥ 10 % of lines are leveled ·
line order preserved · omission note `[tokli: omitted <n> INFO, <n> NOTICE, <n> DEBUG, <n> TRACE lines]`
listing only non-zero counts.

**Omission note (S8a review A6).** The note is the last line of the output. Its line ending is
`\r\n` when every line of the segment ends with `\r\n`, otherwise `\n`. When the segment does
not end with a line break, one of the same kind is inserted before the note.

**Options (S8a-1).**
- `compressors.log_filter.debug_sample` (default 10).
- `compressors.log_filter.apply_to_verbatim_tools` (default false).

**Reason codes:** `not_applicable(too_few_leveled_lines)`; `not_applicable(nothing_omitted)`, when
every line would be kept.

**Claims.** PROVEN: the guarantees above. ASSUMPTION: `omitted_log_lines_not_needed`,
`not_quoted_verbatim`. HEURISTIC: keyword classification and the 10 % gate.

| ID | EARS requirement |
|---|---|
| CP-LF-001 | THE `log_filter` compressor SHALL keep every severe and every unleveled line verbatim and in order. |
| CP-LF-002 | WHEN fewer than 10 % of lines are leveled, THE compressor SHALL report `not_applicable(too_few_leveled_lines)`. |
| CP-LF-003 | WHEN lines are omitted, THE compressor SHALL append an omission note with counts per level. |
| CP-LF-004 | THE compressor SHALL select retained routine lines only by the normalisation and sampling rules above. |

Tests: `test_log_filter_keeps_error_and_warn` · `test_log_filter_keeps_unleveled_lines` ·
`test_log_filter_order_preserved` · `test_log_filter_gate` · `test_log_filter_omission_note` ·
`test_log_filter_normalisation_and_sampling` · `test_log_filter_mixed_keywords_kept_as_severe`.

---

## Transformations not in the v1 catalogue

Prose word deletion, line-template restructuring, JSON null/empty pruning, JSON-to-table
conversion, source-comment stripping, deduplication of arbitrary text blocks, and learned or
third-party compressors are out of scope for v1 (TOKLI_SCOPE.md, non-goals and deferred items).
The hazards behind these decisions are described in TOKLI_EVIDENCE.md (H01, H02, H09).
