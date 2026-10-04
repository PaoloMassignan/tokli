# S8a SCR-003 — A grep line's path must look like a file path

Status: **approved 2026-10-04** ("Approvo scr 003"). Applied to SPEC 010; `search_group` v2.

## 1. Affected requirements

- **SPEC 010 `search_group`, "Grep line" definition** (approved S8a-1): "`<path>` is a POSIX
  path, a Windows drive-letter path or a UNC path containing no `:` other than the drive-letter
  colon".
- CP-SG-001, CP-SG-003, and RT-001 `grep_lines`, which uses the same definition.

## 2. Evidence

- **The smoke run** (`evals/results/2026-10-04-search_group-claude-opus-5-5/report.md`)
  exercised the family `log_verbatim_quote`, whose cases contain no search output at all.
- **The cause:** a log line `2026-10-03 09:00:01 INFO request …` matches the definition, with
  path `2026-10-03 09`, line `00` and content `01 INFO …`. Consecutive lines of the same hour are
  grouped under `[file] 2026-10-03 09`. ISO timestamps (`2026-10-03T09:00:01`) match the same
  way.
- **Consequences:**
  - this is the hazard H11 (look-alike text);
  - the run needed 396 calls instead of 264 and stopped at its cap of 300 with
    `insufficient_data`;
  - the offline saving figure of the S8a-1 report includes such false groups.
- **A related mistake:** during RED a test case `time 10:30:00 something` was removed because
  the approved definition makes it a grep line. The ambiguity should have been raised then.

## 3. Why the requirement should change

The transformation stays lossless, but it is meaningless for the model. It rewrites
timestamps, the most common shape in logs, into fake file headers. That is what the
`not_quoted_verbatim` and `reads_grouped_search` assumptions guard against, and it wastes
evaluation budget.

## 4. Proposed change

The definition of a grep line in SPEC 010 becomes:

> A line of the form `<path>:<line>:<content>`, where `<line>` is one or more ASCII digits and
> `<path>` is a POSIX path, a Windows drive-letter path (`C:\…`, `C:/…`) or a UNC path
> (`\\server\share\…`) that contains no `:` other than the drive-letter colon, **no whitespace,
> and at least one `/`, `\` or `.`**. (S8a SCR-003.)

**Effect:**
- `src/a.py`, `C:\w\x.cs`, `C:/w/x.cs`, `\\srv\share\f.txt` and `README.md` remain grep paths.
- `2026-10-03 09`, `2026-10-03T09`, `Note` and `time 10` are no longer grep paths.
- Bare names without a dot (`Makefile:3:`) and paths with spaces (`C:\Program Files\…`) are no
  longer grouped. That is a missed saving, not an error: the line stays verbatim.

## 5. Impact on tests

New:
- `test_search_group_ignores_timestamps`: `YYYY-MM-DD HH:MM:SS` and ISO `T` forms are not grep
  lines;
- `test_grep_feature_ignores_timestamps`;
- the removed case `time 10:30:00 something`, restored in
  `test_search_group_ignores_non_grep_lines`;
- a case for a path with a space.

`test_s8a1_cases_exercise_their_compressor` gains a check that `search_group` does **not**
exercise the log families, and `log_filter` does not exercise the grep families. The existing
round-trip property is unchanged; its generated paths all contain a separator or a dot.

## 6. Impact on architecture

None. The regular expression in `tokli.compression.text_shapes` changes. It is the single
definition shared by the feature and the compressor.

## 7. Compatibility and migration

- `search_group` version goes to `2`, because its output changes for such lines; the fingerprint
  changes.
- No persisted schema or config key changes.
- The S8a-1 smoke run of `search_group` is repeated after the change: its record is
  `insufficient_data` and is replaced. The offline saving figure is re-measured.
