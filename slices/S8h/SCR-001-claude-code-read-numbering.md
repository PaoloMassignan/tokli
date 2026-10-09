# S8h SCR-001 — `reread_by_reference` must accept the numbering Claude Code actually sends

Status: **approved 2026-10-09** ("approvo"). Found on the human's dogfood dashboard
("Praticamente non filtro nulla": I filter practically nothing).

If approved, the change is carried out as a small slice **S8h** (roadmap entry added on approval).
Approval of this SCR counts as Gate 1. Gate 2 stays as usual.

## 1. Affected requirements and decisions

| Requirement | Approved in | Text |
|---|---|---|
| SPEC 019 **PR-032** | S8e | "THE pruner SHALL apply only to results whose numbered lines all carry the prefix `"{n:>6}\t"` with consecutive numbers; otherwise … `not_applicable(nonstandard_numbering)`." |
| SPEC 019 **PR-034** | S8e | The pruner's decode rebuilds the original result byte for byte. Unchanged, but it now has to cover a second numbering style. |
| **ADR 0013**, "Numbered results only" | S8e | The `cat -n` prefix `"{n:>6}\t"`. |
| **AC-PR-22** | S8e | "a result with another numbering … is not changed, with the stated reason." |

## 2. Evidence (reproducible; metadata and counters only, with the human's consent)

**1. Tokli's own records, last 7 days:**

| | Count |
|---|---|
| Requests | 174 |
| Saved | 0.04 % of input |
| `reread_by_reference` considered | 1,627 |
| `reread_by_reference` applicable | **0** |
| `not_applicable(no_proposal)` | 1,591 (results that are not re-reads) |
| `not_applicable(nonstandard_numbering)` | **36** |

**2. The format of `Read` results in the human's Claude Code sessions,** last 7 days, separator
and field width only:
- 76 numbered results, **all `"<n>\t"` with no left padding** (number field of 1–3 characters);
- 0 in the `cat -n` style `"{n:>6}\t"`;
- 56 results without numbered lines: short notices, images, errors.

**3. The cause, in the code.** `_block()` detects a numbered line with `^ *(\d+)\t`, which accepts
any padding. It then requires every line to start with `f"{n:>6}\t"`. With Claude Code's format
no line passes, and the result is rejected as `nonstandard_numbering`.

**4. Why S8e did not see it.**
- The unit tests, the smoke families, E10(e) and the E2 conversation all generate synthetic reads
  in the `cat -n` style.
- The format was never checked against real Claude Code traffic.
- The smoke record (`no_measurable_damage`) is valid for what it tested, but the compressor has
  never acted on real traffic.

## 3. Why the requirement should change

PR-032 encodes an assumption about the agent's output that is false for the agent Tokli targets
first. The compressor is on by default, and every re-read after an edit is forwarded whole.

Expected effect from the earlier session analysis:
- about 12.7 % of `Read` volume is rebuildable from the request itself;
- that is about 2 % of resent content;
- most of it is priced at the cache-read price, so the money saving stays modest. The dashboard
  will show it.

## 4. Proposed change

**PR-032** becomes:

> PR-032 | THE pruner SHALL apply only to results whose numbered lines all carry the same
> numbering style with consecutive numbers: either `"{n:>6}\t"` (`cat -n`) or `"{n}\t"`
> (Claude Code's `Read`). Otherwise it SHALL report `not_applicable(nonstandard_numbering)`.
> The lines it keeps and the lines that decoding rebuilds SHALL use the result's own style.
> WHEN the style cannot be recovered from the replaced result and its source alone, THE pruner
> SHALL NOT replace it, and SHALL report `not_applicable(ambiguous_numbering)`. Without a source
> it SHALL report `not_applicable(no_source)`, and without a qualifying run
> `not_applicable(no_run)`. (S8h SCR-001.)

**Decode** recovers the style in this order:
1. a numbered line kept in the result;
2. otherwise, the source read's style;
3. otherwise (a `Write` source with every line noted), nothing.

In the last case the pruner does not replace the result, which is the `ambiguous_numbering`
case above. The note format of PR-031 is unchanged.

**AC-PR-22** gains:

> A result numbered `"{n}\t"`, re-read after an edit, is replaced by notes and decodes byte for
> byte; a result mixing the two styles is not changed (`nonstandard_numbering`).

**New regression test.** `test_reread_applies_to_claude_code_numbering` uses an edit and a
re-read in Claude Code's real format. It fails today.

**Product question P1, the smoke record.** The evaluated families use `cat -n` numbering. The
model sees the same notes either way; only the line prefix differs.
- **(a) Recommended:** regenerate the two reread families with Claude Code's numbering and rerun
  the smoke evaluation (run by the human, about the size of the S8e run). This is the first time
  the compressor will really act by default.
- **(b)** Keep the existing record and add the new families later.

## 5. Impact on tests

- **New:** the regression test above.
- **Extended to both styles:** the decode property `prop_reread_by_reference_decodes_whole_request`,
  the source-integrity and prefix-stability tests, and the mixed-style rejection test.
- **Unchanged:** the existing `cat -n` tests.
- **If P1 (a):** `evals/make_cases.py` gains Claude Code numbering for the reread families
  (new case set).

## 6. Impact on architecture

- `tokli.compressors.reread_by_reference` only: the style becomes part of the parsed block.
- ADR 0013 gets an amendment.
- No engine, contract or dependency change.

## 7. Compatibility and migration

- **Version:** `reread_by_reference` goes to version 2, because its output changes on Claude
  Code traffic; the fingerprint changes.
- **No change to:** the persisted schema or config keys.
- **For users:** after the update, a running Claude Code session sees one cache rewrite at the
  first re-read that is now compressed. The re-read had not been sent compressed before, so only
  the new tail changes.
