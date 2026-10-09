# ADR 0013 — Line-range references for re-reads

Status: accepted (S8e, 2026-10-04; approved at S8e Gate 1) · Related: SPEC 009 CC-015, CC-019, CC-021;
SPEC 019 PR-030…PR-036; ADR 0010 (request-scope compressors); TOKLI_EVIDENCE §2 (repeated reads,
E10(e))

## Context

Agents re-read a file after changing a line of it. About 12.7 % of the `Read` volume in the
developer's sessions can be rebuilt exactly from the request itself.

`duplicate_tool_results` refers to an earlier result only when the whole result is
byte-identical. E10(e) showed that a re-read can instead send its changed lines and refer, by
line ranges, to an earlier read for the rest: edit anchors stayed exact (20 of 20) and the
provider did not refuse.

A reference to part of an earlier text is a new contract. It defines what the notes mean, how
the request decodes, and what must stay intact.

## Decision

- **Numbered results only.**
  - The pruner works on results whose lines carry the `cat -n` prefix `"{n:>6}\t"`, numbered
    consecutively.
  - Every other line (headers, `<system-reminder>` blocks) is kept verbatim in place.
  - A result with any other numbering is `not_applicable(nonstandard_numbering)`.
- **Source:**
  - The source is the **latest** earlier record of the same file path in the same request whose
    text is still original: a whole result of a re-read tool, or the `content` of a `Write`.
  - A source that a reference pruner itself changed is never used, so references are never
    chained.
  - Read sources are numbered by their own prefixes; `Write` content is numbered from 1.
- **Alignment:**
  - Runs of at least `pruning.reread_min_run_lines` consecutive numbered lines whose contents
    equal, in order, consecutive source lines are replaced by one note each.
  - The alignment uses `difflib.SequenceMatcher` (standard library, `autojunk=False`).
  - It is deterministic. Any valid alignment is lossless; a better one only saves more.
- **Note:**
  ```text
  [tokli: lines <a>-<b> unchanged — identical to lines <c>-<d> of the read in call <id>]
  ```
  For a `Write` source the note says "of the content written in call <id>". `a`-`b` are the
  result's own line numbers, and `c`-`d` the source's.
- **Decode:** each note is replaced by source lines `c`-`d`, renumbered `a`-`b` with the same
  prefix format. This rebuilds the original result byte for byte (CC-015 for `reference`).
- **Integrity:**
  - The source is registered as a reference target. CC-019 then rejects any later change to it
    that is not byte or structurally equivalent: a Read source is a segment, and a `Write`
    source is an argument string, a segment only when `edit_args_on_resume` exposes it.
- **Bounds:** results or sources above `pruning.reread_max_lines` lines are not considered. This
  keeps the alignment's cost bounded on very large files.

## Alternatives considered

- **Symbol-level notes,** naming the functions. E10(e) showed no gain, and they need parsing per
  language.
- **Chained references** to an earlier re-read that was itself referenced. Rejected: the model
  would have to follow several hops (the same rule as SPEC 019 for duplicates: never name a
  stub).
- **Diff format** (`@@` hunks). Rejected: a patch is a different contract, and the agent would
  have to apply it mentally.

## Consequences

- **Tests:**
  - the property "whole-request decode equals the original";
  - a test per acceptance criterion;
  - a complexity bound like AC-RT-1;
  - compat fixtures unchanged with the pruner off.
- **Prefix-stable:** a note depends only on earlier segments, so a forwarded prefix never
  changes.
- **Portability:** `"\n"` separated lines; a trailing `"\r"` is part of the content and must
  match.
- **Migration:** none (new keys, new compressor, off by default).

## Amendment 2026-10-09 (S8h SCR-001)

**Numbered results** now come in two styles:
- `"{n:>6}\t"` (`cat -n`);
- `"{n}\t"`, the numbering Claude Code's `Read` really sends. The human's sessions showed only
  this style.

**Rules:**
- The style is part of the parsed block. Kept lines, and lines rebuilt by decoding, use the
  result's own style.
- When the style cannot be recovered from the replaced result and its source (a `Write` source
  with every line noted), the result is not replaced (`ambiguous_numbering`).
- The pruner checks its own decode before proposing.
- `reread_by_reference` goes to version 2.

**Lesson recorded in S8h:** the format had been assumed from `cat -n` and never checked against
real traffic. S8h adds format fixtures, a `not_applying` flag and a real-traffic replay.
