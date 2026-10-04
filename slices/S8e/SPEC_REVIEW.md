# S8e — Spec review: re-reads after an edit, sent by reference

Status: **approved 2026-10-04 (Human Gate 1).** The pre-code experiment E10(e) passed. The slice is not yet in `TOKLI_ROADMAP.md`. The human asked for it on 2026-10-04 ("la
modifica è qualcosa su cui investire … modificare una riga o un metodo non dovrebbe comportare
rileggere tutto").

## Why

**Measured on the human's sessions** (TOKLI_EVIDENCE §2, counters only):
- 22.5 % of the code lines that `Read` returns were already in the conversation.
- 12.7 % of the `Read` volume is a re-read that can be rebuilt exactly from the conversation:
  - 10.4 %: the last read with the agent's edits applied;
  - 2.3 %: the agent's own `Write`;
  - 1.6 % more is an unchanged repeat, which `duplicate_tool_results` already covers when it is
    whole.

**E10(e):**
- A re-read that sends only the changed lines and refers to the earlier read for the unchanged
  runs kept every edit anchor exact: 20 of 20, the same as the whole file.
- It drew no refusal and cut the request by 42 % in that setting.
- The information stays in the request, which is the condition every successful form shared
  (E11, E10(e)), and the failed ones lacked (E10(c), E10(d)).

## Proposed behaviour

A request-scope pruner, `reread_by_reference`: **LOSSLESS, equivalence `reference`**,
prefix-stable.
- **Which results:** for a `Read` result whose file was read earlier in the same request (a full
  or ranged `Read` result, or the content of a `Write` to the same path), the pruner compares the
  new result with that earlier text, line by line.
- **Unchanged runs** of at least `pruning.reread_min_run_lines` lines (default 5) become one note:
  ```text
  [tokli: lines <a>-<b> unchanged — identical to lines <c>-<d> of the read in call <id>]
  ```
  The note says "of the content written in call <id>" when the source is a `Write`.
- **Every other line** is kept verbatim, with its `cat -n` number.
- **Protected spans** (the `<system-reminder>` Claude Code appends to some reads, 88 of 1,781)
  are kept verbatim after the notes.
- **The source must still be in the request and unchanged,** checked at run time by reference
  integrity (CC-019). The decision for a result depends only on earlier segments (prefix-stable),
  so it never rewrites history.
- **Decoding** the whole request rebuilds the original result byte for byte (CC-015 for
  `reference`).

## Relation to what exists

- **`duplicate_tool_results`** runs first (same stage, by id). A whole identical result is still
  stubbed by it; this pruner handles the partial cases.
- **`verbatim_tools`:** `Read` is in it. Like the duplicate pruner, this one is exempt (CC-021),
  because the exact bytes stay in the earlier copy. That is the assumption the evaluation must
  check.
- **`edit_args_on_resume`** (off, not recommended): a `Write` used as a source becomes a reference
  target, so CC-019 rejects any later attempt to stub it.

## Spec delta to write for Gate 1

- **SPEC 019:**
  - a section `reread_by_reference`, PR-030 onwards: rule, note format, sources, minimum run,
    protected spans, decode, prefix stability;
  - acceptance criteria and test names.
- **SPEC 010:** a catalogue row; the assumption `reads_partial_reference` (the model reads the
  current file from the changed lines plus the referenced earlier lines, and copies anchors from
  there).
- **SPEC 012:** two families:
  - `reread_edit_anchor`: the E10(e) shape. The checker `edit_anchor` passes when the response is
    an `Edit` whose `old_string` occurs exactly once in the current file and holds the target
    line;
  - `reread_fact_lookup`: a value from an unchanged region (`exact_value` or `answer_or_read`).
- **SPEC 017:** `compressors.reread_by_reference.enabled`, `pruning.reread_min_run_lines`.
- **ADR 0013:** the line-level reference format and its decoder. This is a new reference form, by
  line ranges, so its decode and integrity rules are a contract.

## Product questions → for the human

1. **P1 — Note format:** the plain note (as E10(e) `reference`), without function names.
   **Recommended:** the names added nothing (20/20 both ways) and the plain form works for every
   language.
2. **P2 — Sources:** earlier `Read` results of the same path **and** the content of a `Write` to
   it. **Recommended:** together they cover 12.7 % of the `Read` volume, against 10.4 % for reads
   alone.
3. **P3 — Default:** off until its smoke record exists. Then on by default if the record says
   `no_measurable_damage` (CC-020), as for the duplicate pruner. **Recommended.**
4. **P4 — Minimum run** of 5 lines. **Recommended.**

## Scope check

- No change to CC-006 or PR-005: only the content of a tool result changes, as for duplicates.
- No conversation state is needed.
- No new dependency: the diff uses the standard library's `difflib` (a linear-time variant to be
  checked for very large files: a complexity test like AC-RT-1).

### Answers (2026-10-04)

The human: "Accetto". P1…P4 are accepted as recommended:
- the plain note;
- `Read` and `Write` sources;
- off until the smoke record, then on by default if it allows it;
- runs of at least 5 lines.

## Spec delta (written for Gate 1; status lines read "pending S8e Gate 1")

| File | Change |
|---|---|
| SPEC 019 | New section `reread_by_reference`: rule, note, decode, claims. PR-030…PR-036, AC-PR-20…AC-PR-26, test names. |
| SPEC 010 | Catalogue row; the assumption `reads_partial_reference`. |
| SPEC 012 | Families `reread_fact_lookup` and `reread_edit_anchor`; the checker `edit_anchor`. |
| SPEC 017 | "Keys added in S8e": four keys. |
| SPEC 009 | A note: CC-019 covers line-range references, and a `Write` argument used as a source is a reference target. |
| TOKLI_ROADMAP | S8e entry. |
| ADR 0013 | Line-range references (proposed). |

**Implementation decision, recorded:** a note never points to a re-read that was itself
referenced (PR-033), the same rule as for duplicates.

**Fix found while writing the delta:** inserting the S8c section into SPEC 019 had deleted the
heading "Default tool semantics (config data, revisable)", already on `main` since S8c. It is
restored here. The content of that table did not change.

Gate 1 record: **approved 2026-10-04**, the human's words: "Approvo" (answering the request to
approve S8e and ADR 0013). Spec delta: the table above. ADR 0013 accepted.
