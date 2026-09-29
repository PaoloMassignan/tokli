# TOKLI — The compressors, one by one

This guide explains, in plain terms, every compression tool planned for Tokli v1: what problem it
solves, how it works, what it looks like on a real example, what Tokli can prove about it, and
what it only assumes. It is **explanatory**. The normative text is in SPEC 009 (contract and
preservation model), SPEC 010 (catalogue) and SPEC 019 (tool-history pruning). If this guide and a
spec disagree, the spec wins, and this guide must be fixed.

## 1. Basics you need for the rest

**Where compressors work.** A request from a coding agent contains a conversation. Tokli splits it
into *segments*: the text values it may change. In v1 a compressor only ever touches:

- **tool results**: what a tool returned to the agent (file contents, command output, search
  results, JSON from an API);
- **user text**: text typed or injected into user turns.

It never touches system instructions, tool definitions, the model's own messages, images, the
model's reasoning, or anything in the response.

**Two kinds of compressor.**

- **Segment compressors** look at one segment at a time: `json_minify`, `search_group`,
  `dictionary`, `diff_context_trim`, `log_filter`.
- **Request compressors ("pruners")** look at the whole tool history of the request:
  `duplicate_tool_results`, `superseded_tool_results`. They never delete a tool call or a message.
  They replace the *content* of a tool result with a short **stub**.

**Order.** Pruners run first, so no work is wasted compressing a result that will become a stub.
Then segment compressors run in a fixed order: `normalize` (json_minify) → `structural`
(search_group) → `domain` (dictionary, diff_context_trim, log_filter). Within a stage the order is
alphabetical by id.

**Rules that apply to every compressor** (enforced once by the engine, not by each compressor):

| Rule | Meaning |
|---|---|
| Shrink or nothing | A result is kept only if it saves at least 4 tokens **and** at least 1 % of the segment. Otherwise the original text stays. |
| Never longer | No segment, and no request, is ever forwarded longer than the original. |
| Protected text | Text marked protected (for example `<system-reminder>…</system-reminder>` blocks) must come out unchanged and in order, or the result is rejected. |
| Verbatim tools | Results of tools whose output agents often copy back byte-for-byte (default `Read`, `Bash`, `shell`, `shell_command`, `container.exec`) are not transformed. The one exception is `duplicate_tool_results`, because it leaves the original bytes in place (§3). |
| Failure is harmless | If a compressor crashes or is too slow, the text stays as it was, and the failure is recorded. The request always goes through. |
| Deterministic | Same input and same configuration give the same output, on every machine. |
| Measured | For every request and compressor, Tokli records how many segments it looked at, how many it changed, the tokens it saved and the time it took. |

**Preservation classes**: what Tokli can *prove*.

| Class | What is proven | Example |
|---|---|---|
| Lossless · exact | The original can be rebuilt byte for byte from the output alone. | `search_group`, `dictionary` |
| Lossless · structural | The output means exactly the same under a precise parser, and only bytes that the parser ignores were removed. | `json_minify` (JSON whitespace) |
| Lossless · by reference | The removed text is still present, identical, earlier in the same request, and the stub names where. | `duplicate_tool_results` |
| Selective | A declared part is kept verbatim; the rest is removed. It cannot be undone. | `superseded_tool_results`, `diff_context_trim`, `log_filter` |
| Lossy | Nothing is guaranteed beyond the engine rules. | none in v1 |

**Assumptions**: what Tokli can *not* prove. Every compressor relies on something about the
model's behaviour, for example "the model reads minified JSON as well as indented JSON". These
assumptions are named for each compressor below. A compressor may be **on by default** only after
an evaluation has checked its assumptions (SPEC 012). The policy switch cares only about the
proven class:

- **LOSSLESS ONLY** (default): only the three lossless classes may run.
- **LOSSY ALLOWED**: selective and lossy compressors may run too, when enabled.

## 2. Summary

| Compressor | What it does, in one line | Class | Default | Slice |
|---|---|---|---|---|
| `json_minify` | Removes indentation and line breaks from JSON | lossless · structural | on (provisional until evaluated) | S1 |
| `duplicate_tool_results` | Replaces a tool result identical to an earlier one with a one-line pointer | lossless · by reference | on only if its evaluation passes | S4 |
| `search_group` | Writes the file path once for a run of search matches in the same file | lossless · exact | off | S8 |
| `dictionary` | Replaces long phrases repeated in a segment with short symbols plus a legend | lossless · exact | off | S8 |
| `superseded_tool_results` | Replaces an old file read with a stub when a newer full version exists later | selective | off (LOSSY ALLOWED only) | S8 |
| `diff_context_trim` | Keeps every changed line of a diff, and only 1 unchanged line around each change | selective | off (LOSSY ALLOWED only) | S8 |
| `log_filter` | Keeps every error, warning and unlabelled log line, and drops repeated routine lines | selective | off (LOSSY ALLOWED only) | S8 |

---

## 3. `json_minify`

**In one sentence.** Removes the spaces, indentation and line breaks that make JSON readable for
humans but mean nothing to a JSON parser.

**Problem.** Tools often return pretty-printed JSON (API responses, MCP tools). Indentation can be
a large share of its tokens.

**How it works.**
1. It runs only if the whole segment is valid, strict JSON and contains some removable whitespace.
2. It copies the text character by character. Outside strings it drops spaces, tabs and line
   breaks. Inside strings it copies everything exactly.
3. It never re-formats values. `1.0` stays `1.0`, `\u00e9` stays `\u00e9`, key order and duplicate
   keys are kept.

**Example**

Before:
```json
{
  "name": "tokli",
  "version": "1.0",
  "note": "two  spaces stay",
  "tags": [
    "proxy",
    "tokens"
  ]
}
```
After:
```json
{"name":"tokli","version":"1.0","note":"two  spaces stay","tags":["proxy","tokens"]}
```

**Proven.** Parsing the output gives exactly the same JSON value as parsing the input, with numbers
compared by their spelling and duplicate keys kept (tested with randomly generated JSON on every
commit). It runs in linear time.

**Assumed.** The model understands minified JSON as well as indented JSON (`reads_minified_json`).
The agent never needs to copy this output back byte-for-byte (`not_quoted_verbatim`).

**Does not run when.** The segment is not only JSON (text before or after it, invalid JSON, `NaN`),
the JSON has no removable whitespace, the tool is in the verbatim list, or the saving is too small.

**Settings.** `compressors.json_minify.enabled`; the shared `compression.verbatim_tools` list.

**Risks.** An agent that must reproduce the JSON exactly (for example to edit a JSON file it just
read through a non-verbatim tool) might copy the minified form. That is why file-reading tools are
on the verbatim list, and why the smoke evaluation checks JSON quoting.

---

## 4. `duplicate_tool_results`

**In one sentence.** When a tool returns exactly the same result it (or another tool) already
returned earlier in the conversation, the later copy becomes a one-line pointer to the earlier
one.

**Problem.** Agents re-read the same files and re-run the same commands. Every turn resends the
whole history, so each identical copy is paid for again and again.

**How it works.**
1. For each tool result, it looks for an earlier tool result in the same request with
   byte-identical text. It considers only results of at least 64 tokens.
2. If there is one, the later result's content is replaced by a stub that names the **earliest**
   identical result by its tool-call id.
3. The earliest copy is never changed. The tool call, the result block and all ids stay in place,
   so the conversation keeps its structure.

**Example**

A conversation in which the agent reads the same unchanged file twice:

```text
turn 3   tool call  toolu_01  Read src/app.py
         result     <1,200 tokens of src/app.py>
...
turn 9   tool call  toolu_07  Read src/app.py
         result     <the same 1,200 tokens>
```
What is forwarded:
```text
turn 3   tool call  toolu_01  Read src/app.py
         result     <1,200 tokens of src/app.py>            (unchanged)
...
turn 9   tool call  toolu_07  Read src/app.py
         result     [tokli: identical to the result of tool call toolu_01 earlier in this conversation — 1200 tokens omitted]
```

**Why the later copy, not the earlier one?** Providers cache the beginning of a conversation.
Changing something that was already sent (the earlier copy) would force the provider to re-write
its cache, which costs more than it saves. The stub is created the first time the duplicate
appears and never changes afterwards (**prefix-stable**).

**Proven.** Every stubbed text is still present, identical, earlier in the same request.
Replacing each stub with the text it names rebuilds the original request exactly. At run time Tokli
also checks that nothing later removes or changes the referenced original (**reference
integrity**). If another compressor tries, that change is rejected.

**Assumed.** The model understands that the stub means "same content as call toolu_01" and answers
from there (`resolves_result_reference`). When it must copy the content exactly, for example as an
edit anchor, it copies it correctly from the earlier copy (`quotes_from_reference_target`). Both
are checked by the smoke evaluation in S4 (experiment E11) before this compressor is turned on by
default.

**Verbatim tools.** This is the only compressor that also works on `Read`/`Bash` results, because
the exact bytes remain available in the earlier copy.

**Does not run when.** No earlier identical result exists, the result is under 64 tokens, or,
with `duplicate_require_same_call: true`, the two calls differ in tool name or arguments.

**Settings.** `compressors.duplicate_tool_results.enabled`, `pruning.duplicate_min_tokens` (64),
`pruning.duplicate_require_same_call` (false).

**Risks.** The earlier copy may be far back in a long conversation, and a model could pay less
attention to it. This is exactly what the evaluation measures.

---

## 5. `search_group`

**In one sentence.** In grep/ripgrep output, writes each file path once for a run of matches in
the same file, instead of on every line.

**Problem.** Search output repeats the full path on every matching line.

**How it works.**
1. A *grep line* looks like `<path>:<line number>:<content>`. Paths may be POSIX
   (`src/app.py`), Windows (`C:\repo\app.py`) or network (`\\server\share\app.py`).
2. It runs only if the segment has at least 5 grep lines.
3. Two or more consecutive grep lines with the same path become a `[file] <path>` header followed
   by indented `<line>:<content>` lines.
4. Every other line (separators `--`, headings, prose) stays exactly where it was.
5. If an original line could be confused with the new format (it starts with `[file] `, with `\`,
   or with two spaces and digits and a colon), it is escaped with a leading `\`.

**Example**

Before:
```text
src/app.py:12:def load():
src/app.py:40:    load()
src/app.py:77:    return load()
--
tests/test_app.py:5:from app import load
tests/test_app.py:9:    load()
```
After:
```text
[file] src/app.py
  12:def load():
  40:    load()
  77:    return load()
--
[file] tests/test_app.py
  5:from app import load
  9:    load()
```

**Proven.** The original is rebuilt byte for byte from the output, including Windows and mixed
line endings. No line is lost or moved.

**Assumed.** The model attributes each match to the right file and line (`reads_grouped_search`).
The agent does not copy the grouped form back (`not_quoted_verbatim`).

**Does not run when.** Fewer than 5 grep lines, no run of 2+ lines with the same path, a verbatim
tool, or too little saving.

**Settings.** `compressors.search_group.enabled`, `min_group_lines` (5).

**Risks.** Tools that expect `path:line:` on every line would see a different format. Off by
default until an evaluation (E8) shows no harm.

---

## 6. `dictionary`

**In one sentence.** When the same long phrase appears many times in one segment, it is replaced
by a short symbol, and a small legend at the top says what each symbol means.

**Problem.** Some outputs (repeated warnings, boilerplate messages) contain the same long phrase
many times.

**How it works.**
1. **Candidates** are runs of at least 3 words on one line, at least 20 characters long, that
   contain no digit and do not touch protected text, URLs or quoted strings. A candidate must
   appear at least 3 times.
2. It repeatedly picks the candidate that saves the most tokens (counting the cost of its legend
   line), with fixed tie-breaks, and replaces it everywhere. It stops when nothing saves at least
   1 token, or after 26 entries.
3. Symbols are `§A` to `§Z`. The legend sits at the start of the same segment, between
   `[tokli:dict]` and `[tokli:text]`.
4. It does not run if the text already contains something like `§A` or the markers, so decoding
   can never be ambiguous.

**Example**

Before:
```text
WARNING could not reach the package registry mirror, falling back
WARNING could not reach the package registry mirror, falling back
WARNING could not reach the package registry mirror, falling back
WARNING could not reach the package registry mirror, falling back
```
After:
```text
[tokli:dict]
§A=WARNING could not reach the package registry mirror, falling back
[tokli:text]
§A
§A
§A
§A
```

**Proven.** Expanding the symbols (last assigned first) rebuilds the original byte for byte.
Nothing inside protected text, URLs, quoted strings or phrases with digits is ever replaced.

**Assumed.** The model expands the symbols correctly when it reasons about or quotes the text
(`applies_dictionary_legend`). This is the weakest assumption of all the lossless compressors:
the model has to "decode" in its head.

**Does not run when.** No phrase repeats enough to pay for its legend, collision markers are
present, a verbatim tool, or too little saving.

**Settings.** `compressors.dictionary.enabled`, `min_phrase_words` (3), `min_phrase_chars` (20),
`min_occurrences` (3), `max_entries` (26).

**Risks.** Wrong answers if the model misreads a symbol. Off by default until experiment E7.

---

## 7. `superseded_tool_results` (selective)

**In one sentence.** When the agent read a file and later read or rewrote the **whole** file
again, the older, outdated content is replaced by a short note.

**Problem.** In long sessions agents read a file, change it, and read it again. The older versions
stay in the history and are resent on every turn, although they no longer describe the file.

**How it works.**
1. Tool meaning comes from configuration, not code: for example Claude Code's `Read` reads
   `file_path`; `Write` writes a whole file with its content in the arguments; `Edit` changes part
   of a file. Codex shell commands are classified by fixed rules (`cat`, `Get-Content`, `head`,
   `tail` read; `apply_patch`, `Set-Content`, `Out-File` write), and anything else is "other".
2. An earlier read of file X is **superseded** if a later tool call reads all of X again, or writes
   all of X with the content visible in its arguments. Partial reads only supersede the same range.
   An edit never supersedes, because the earlier read is still needed to know the file's state.
3. To limit cache damage, it acts only when the newer read or write is itself at least 4 user
   turns old (PR-007), and only when the whole request saves at least 8,000 tokens.

**Example**

```text
turn 2    toolu_02  Read config.yaml   → <old contents, 3,000 tokens>
turn 5    toolu_09  Edit config.yaml   → ok
turn 12   toolu_15  Read config.yaml   → <new contents, 3,100 tokens>
```
Forwarded in a later request, once turn 12 is at least 4 user turns old and the request-wide saving reaches 8,000 tokens:
```text
turn 2    toolu_02  Read config.yaml   → [tokli: outdated contents of config.yaml omitted — a newer full read/write appears later (call toolu_15)]
turn 5    toolu_09  Edit config.yaml   → ok
turn 12   toolu_15  Read config.yaml   → <new contents>      (unchanged)
```

**Proven (the retention rule).** The latest full view of every file stays verbatim. Results of
unknown tools are never touched. The conversation structure is unchanged. If a result is the
original that a duplicate stub points to, it is never stubbed (reference integrity).

**Not proven, so selective.** The old version is gone. The model can no longer see what the file
looked like before the change.

**Assumed.** Once a newer full view exists, the model does not need the old one
(`outdated_content_not_needed`).

**Cache cost.** Unlike every other compressor, this one changes history that was already sent.
The request is flagged `history_rewritten`, and the UI marks the compressor "may invalidate
provider cache". Experiment E2-ext measures whether the saving outweighs the extra cache writes.

**Settings.** `compressors.superseded_tool_results.enabled`, `pruning.superseded_min_age_turns`
(4), `pruning.superseded_min_saving_tokens` (8,000), `pruning.tool_semantics`.

---

## 8. `diff_context_trim` (selective)

**In one sentence.** In a unified diff, keeps every header and every added or removed line, but
only one unchanged line of context around each change.

**Problem.** Diffs usually carry 3 unchanged lines before and after each change, which often
outweigh the change itself.

**How it works.** It runs only on text that has the shape of a diff. It keeps all header lines
(`diff --git`, `index`, `---`, `+++`, `@@`) and all `+`/`-` lines, keeps at most 1 unchanged line on
each side of a change, keeps any trailing text that is not part of a hunk, and adds a note with
the number of omitted lines.

**Example** (`max_context` = 1)

Before:
```diff
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,7 +10,7 @@
 import os
 import sys
 
-TIMEOUT = 5
+TIMEOUT = 30
 
 def main():
     run()
```
After:
```diff
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,7 +10,7 @@
 
-TIMEOUT = 5
+TIMEOUT = 30
 
[tokli: 4 context lines omitted]
```

**Proven (the retention rule).** Every header and every changed line is kept verbatim. Text after
the diff is never swallowed. Look-alike text (Markdown or YAML lists, `+`/`-` in prose) is not
treated as a diff.

**Not proven, so selective.** The removed context is gone. The `@@` line counts no longer match
the body, so the output is not a patch that can be applied.

**Assumed.** The model does not need the removed context, and nobody applies the trimmed diff
mechanically (`context_lines_not_needed`).

**Settings.** `compressors.diff_context_trim.enabled`, `max_context` (1).

---

## 9. `log_filter` (selective)

**In one sentence.** In application logs, keeps every error, warning and unlabelled line, keeps
the first line of each repeated routine message, and samples debug lines.

**Problem.** Logs repeat the same INFO/DEBUG message with different numbers thousands of times.

**How it works.**
1. It runs only if at least 10 % of the lines carry a level word (`ERROR`, `WARN`, `INFO`, `DEBUG`, …).
2. A line with any of `FATAL`, `CRITICAL`, `ERROR`, `EXCEPTION`, `WARN`, `WARNING` is **severe**
   and always kept, even if it also says `INFO`. A line with no level word (e.g. a stack trace) is
   always kept.
3. Routine lines are grouped by **pattern**: the line with every run of digits (and long hex ids)
   replaced by `#`. For INFO/NOTICE only the first line of each pattern is kept. For DEBUG/TRACE
   the 1st, 11th, 21st … are kept.
4. Order is preserved, and a note counts what was omitted per level.

**Example**

Before:
```text
2026-09-29 10:00:01 INFO request 1041 served in 12 ms
2026-09-29 10:00:02 INFO request 1042 served in 9 ms
2026-09-29 10:00:03 INFO request 1043 served in 15 ms
2026-09-29 10:00:03 DEBUG cache hit key=user:77
2026-09-29 10:00:04 ERROR request 1044 failed: timeout after 30 s
Traceback (most recent call last):
  File "server.py", line 88, in handle
```
After:
```text
2026-09-29 10:00:01 INFO request 1041 served in 12 ms
2026-09-29 10:00:03 DEBUG cache hit key=user:77
2026-09-29 10:00:04 ERROR request 1044 failed: timeout after 30 s
Traceback (most recent call last):
  File "server.py", line 88, in handle
[tokli: omitted 2 INFO lines]
```

**Proven (the retention rule).** Every severe and every unlabelled line is kept verbatim and in
order. The omission note is always present when something was dropped.

**Not proven, so selective.** The dropped routine lines are gone. Their exact numbers (timings,
ids) are no longer visible.

**Assumed.** The dropped lines are not needed for the task (`omitted_log_lines_not_needed`).

**Settings.** `compressors.log_filter.enabled`, `debug_sample` (10).

---

## 10. What Tokli deliberately does not do (v1)

| Idea | Why not |
|---|---|
| Deleting "unimportant" words from prose (articles, connectives) | Corrupts code, for example identifiers named `a` or `the`, and indentation (TOKLI_EVIDENCE H01) |
| Re-formatting JSON by parsing and re-printing it | Changes numbers, escapes and duplicate keys (H09) |
| Dropping `null` or empty fields from JSON | Absent and `null` mean different things |
| Turning JSON arrays into tables | Types become ambiguous |
| Stripping comments from source code | Agents quote code back exactly (H04) |
| Removing whole tool calls or shortening their arguments | Protocol pairing rules and provider validation (H07, H08); experiment E10 first |
| Deduplicating arbitrary text blocks by removing the earlier copy | Breaks provider caching (H05). `duplicate_tool_results` does it the cache-safe way. |
| Learned or model-based compressors | Heavy, machine-dependent, and poor on code in the available benchmarks |
| Compressing system instructions or tool definitions | Usually cached cheaply, and they are instructions (Q1) |

## 11. Reading the numbers on the dashboard

- **Marginal saving** is what a compressor saved *after* the ones before it in the chain.
  The per-compressor figures add up exactly to the total saving.
- **Zero-benefit rate** is how often a compressor ran on a segment but its result was not kept.
  A high rate plus noticeable latency means that it costs time for nothing.
- **Tokens saved per ms** shows efficiency.
- **Skipped (budget)** counts how often a compressor was skipped because the request's time budget
  was used up. It is visible so that a useful but slow compressor is never hidden.
- Each figure carries its method: **exact** (from the provider), **calibrated**, or **estimate**.
