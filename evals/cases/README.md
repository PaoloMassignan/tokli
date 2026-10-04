# Smoke-tier evaluation cases (SPEC 012, QE-013)

Synthetic, protocol-shaped Anthropic Messages requests. They contain no real prompts, paths or
keys. They are written by `evals/make_cases.py` (fixed seeds) and reviewed in the pull request.
Every case file has these fields:

- `case_set`;
- `family`;
- `assumption` (the assumption id it tests);
- `checker` (`exact_value`, `json_structural` or `verbatim_line`, QE-020);
- `request`: the body without `model`, which comes from `--model`;
- `expected`: a string; for `json_structural` it is JSON text.

In the JSON families every tool name is a non-verbatim tool and every tool result is well above
64 tokens, so `json_minify` can apply. In the reference families the repeated read is `Read`, a
verbatim tool, which the reference pruner still handles (CC-021). A case it leaves unchanged is reported as `not_exercised` (QE-012).

| Family | Assumption | Task | Checker |
|---|---|---|---|
| `json_fact_lookup` | `reads_minified_json` | One value from a pretty-printed JSON tool result (an id, SKU, price, quantity, commit, duration) | `exact_value` |
| `json_verbatim_quote` | `not_quoted_verbatim` | The complete JSON object of one entry, to pass to another tool | `json_structural` |
| `reference_fact_lookup` (S4) | `resolves_result_reference` | A file read twice, another tool in between; a value from the latest read, which `duplicate_tool_results` stubs | `exact_value` |
| `reference_verbatim_quote` (S4) | `quotes_from_reference_target` | The same history; the exact line holding a key, leading whitespace kept and the line-number prefix left out (an edit anchor) | `verbatim_line` |
| `grep_fact_lookup` (S8a-1) | `reads_grouped_search` | Search output over 3–5 files (POSIX, Windows drive-letter or UNC paths); the `<path>:<line>` of the match with a marker | `exact_value` |
| `grep_verbatim_quote` (S8a-1) | `not_quoted_verbatim` | The same output; the content of the marked match line, without the path and line-number prefix, leading whitespace kept (an edit anchor) | `verbatim_line` |
| `log_fact_lookup` (S8a-1) | `omitted_log_lines_not_needed` | A service log of 80–120 lines, mostly repeated INFO and DEBUG lines; the error code of the marked failed request | `exact_value` |
| `log_verbatim_quote` (S8a-1) | `not_quoted_verbatim` | The same log; the full marked ERROR line | `verbatim_line` |

The S8a-1 families (case set `2026-10-03.2`) put their content in tools outside the default
`verbatim_tools` (`Grep`, `service_logs`), so `search_group` and `log_filter` apply with their
default options. Whether models cope with the same transformations of `Bash` output is E8 (S8b).
Families that share an assumption (`not_quoted_verbatim`) are loaded for every compressor that
declares it; a compressor that does not change a case reports it as `not_exercised` and makes no
call for it (QE-012).

22 cases per family. The verdict needs 20 completed cases (`smoke_min_cases`, QE-015).
