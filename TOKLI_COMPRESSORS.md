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
  `duplicate_tool_results`, `reread_by_reference`, `superseded_tool_results`, `edit_args_on_resume`.
  They never delete a tool call or a message.
  - The first two replace the *content* of a tool result with a short **stub**.
  - `edit_args_on_resume` replaces old strings inside the *arguments* of `Write`/`Edit` calls.

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
| Verbatim tools | Results of tools whose output agents often copy back byte-for-byte (default `Read`, `Bash`, `shell`, `shell_command`, `container.exec`) are not transformed. Exceptions: `duplicate_tool_results`, because it leaves the original bytes in place (§4); and a compressor for which the user switched on **"Also on Read, Bash…"** (`apply_to_verbatim_tools`, off by default; today `search_group` and `log_filter` offer it). A result whose tool name is unknown is always treated as verbatim. |
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
an evaluation has checked its assumptions (SPEC 012), and a selective or lossy one is never on by
default in v1.

**Switching compressors.**
- Enabling a compressor is the only control (S4 SCR-001). Its class does not block it.
- **"Lossless only"** on the Settings page is a shortcut: it switches off every enabled
  compressor that is not lossless.
- Each request records `LOSSLESS_ONLY` when only lossless compressors were on, and
  `LOSSY_ALLOWED` otherwise.

**Evaluation status.** Each compressor shows its evaluation record: none, or `smoke` with a
verdict. A smoke evaluation detects only gross damage. Each family of test cases checks one
assumption; a family whose cases a compressor never changes is reported `not_exercised` and does
not count (S8a SCR-002).

## 2. Summary

| Compressor | What it does, in one line | Class | Default | Evaluation (smoke, `claude-opus-5-5`) | Status |
|---|---|---|---|---|---|
| `json_minify` | Removes indentation and line breaks from JSON | lossless · structural | on | no measurable damage (2026-10-03) | built (S1) |
| `duplicate_tool_results` | Replaces a tool result identical to an earlier one with a one-line pointer | lossless · by reference | on | no measurable damage (E11, 2026-10-03) | built (S4) |
| `search_group` | Writes the file path once for a run of search matches in the same file | lossless · exact | off | no measurable damage (v2, 2026-10-04) | built (S8a-1) |
| `reread_by_reference` | When a file is read again after a change, sends only the changed lines and points to the earlier read for the rest | lossless · by reference | **on** | no measurable damage (2026-10-04) | built (S8e) |
| `log_filter` | Keeps every error, warning and unlabelled log line, and drops repeated routine lines | selective | off (never on by default in v1) | no measurable damage (2026-10-04) | built (S8a-1) |
| `dictionary` | Replaces long phrases repeated in a segment with short symbols plus a legend | lossless · exact | off | — | planned (S8a-2) |
| `diff_context_trim` | Keeps every changed line of a diff, and only 1 unchanged line around each change | selective | off | — | planned (S8a-2) |
| `superseded_tool_results` | Replaces an old file read with a stub when a newer full version exists later | selective | off | — | planned (S8a-3) |
| `edit_args_on_resume` | After a long pause, replaces the text of old `Write`/`Edit` calls with a one-line stub | selective | off — **not recommended** | **damage detected** (refusals, 2026-10-04) | built (S8c) |

What these compressors save on real Claude Code traffic is in §12.

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

**On real traffic.** On Claude Code traffic it found almost nothing to do: JSON-shaped results
are about 1 % of the tool-result volume, and most of them come from `Bash`, a verbatim tool (§12).

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
are checked by the smoke evaluation in S4 (experiment E11). The verdict was "no measurable
damage" (132 of 132 candidate answers correct), so it is on by default.

**Verbatim tools.** This is the only compressor that also works on `Read`/`Bash` results, because
the exact bytes remain available in the earlier copy.

**Does not run when.** No earlier identical result exists, the result is under 64 tokens, or,
with `duplicate_require_same_call: true`, the two calls differ in tool name or arguments.

**Settings.** `compressors.duplicate_tool_results.enabled`, `pruning.duplicate_min_tokens` (64),
`pruning.duplicate_require_same_call` (false).

**Risks.** The earlier copy may be far back in a long conversation, and a model could pay less
attention to it. This is exactly what the evaluation measures.

**On real traffic.** Claude Code already answers a second `Read` of an unchanged file with a short
"unchanged" message, so the real gain is mostly on repeated shell output, and it is modest (§12).

---

## 4a. `reread_by_reference` (S8e)

**Claude Code's numbering (S8h).** Claude Code's `Read` puts the line number, then a tab, before
each line, with no padding (`"1\t…"`). Version 1 read only the `cat -n` style, where the number
is padded to six characters (`"     1\t…"`), so it never acted on real Claude Code traffic.
Version 2 reads both, and rebuilds each result in its own style. Its smoke record (2026-10-09,
Claude Code's numbering) shows no measurable damage, so it is on by default.

**With `duplicate_tool_results` (S6 SCR-001).** When a later read is identical to an earlier
re-read, the earlier re-read keeps its notes. The duplicate stub that would have pointed at
it is reverted, and the later read becomes notes too. Otherwise the earlier re-read would be
sent whole again, and the provider would rewrite its cache from there.

**In one sentence.** When the agent reads a file again after changing a line of it, only the
changed lines are sent; every unchanged run of lines becomes a one-line pointer to the same lines
in the earlier read.

**Problem.** After editing a method, agents read the whole file again to check it. Claude Code
skips a re-read only when the file is unchanged, so after any edit the whole file is resent, and
then resent again on every turn. In the developer's sessions, 12.7 % of what `Read` returns
could be rebuilt exactly from the conversation itself.

**How it works.**
1. **Source:** for a `Read` of a file that the conversation already holds (an earlier `Read`, or
   the content of the agent's own `Write`), the pruner takes the latest copy that is still
   original. It never takes a re-read that was itself turned into pointers.
2. **Comparison:** it compares the new read with that copy line by line. Each run of at least 5
   identical lines becomes one note; changed lines stay in full, with their line numbers.
3. **What stays:** anything else in the result, such as a `<system-reminder>` that Claude Code
   appends, stays verbatim.

**Example** (one line inserted after line 30 of a 60-line file):

```text
[tokli: lines 1-30 unchanged — identical to lines 1-30 of the read in call toolu_07]
    31	    base = round(base, 3)
[tokli: lines 32-61 unchanged — identical to lines 31-60 of the read in call toolu_07]
```

**Proven.**
- Replacing every note with the lines it names rebuilds the original read byte for byte.
- At run time Tokli checks that the earlier copy is still there and unchanged (reference
  integrity).
- The decision is made when the re-read first appears and never changes, so the provider cache
  stays valid.

**Assumed.**
- The model reads the file as "changed lines plus the referenced earlier lines"
  (`reads_partial_reference`).
- When it must quote an unchanged line exactly, for example as an edit anchor, it copies it
  correctly from the earlier read (`quotes_from_reference_target`).

Experiment E10(e) on `claude-opus-5-5`: 20 of 20 edits with exact anchors, no refusal, and a
request 42 % smaller.

**Does not run when.**
- There is no earlier copy of the file in the request.
- No run of 5 identical lines exists.
- The line numbering is not the standard `cat -n` one.
- The file is above 20,000 lines.

**Evaluation.** Smoke, 2026-10-04: no measurable damage in all three families (re-read facts,
exact edit anchors, verbatim quotes), no refusal, 40 % fewer input tokens on those cases. It is
on by default.

**Settings.** `compressors.reread_by_reference.enabled` (on),
`pruning.reread_tools` (`Read`), `pruning.reread_min_run_lines` (5), `pruning.reread_max_lines`
(20,000).

**Why this works when pruning did not.** Every form that **removed** information from the
conversation drew provider refusals (S8c, S8d). This one removes nothing: the earlier read is
still in the request, as with `duplicate_tool_results`.

## 5. `search_group`

**In one sentence.** In grep/ripgrep output, writes each file path once for a run of matches in
the same file, instead of on every line.

**Problem.** Search output repeats the full path on every matching line.

**How it works.**
1. A *grep line* looks like `<path>:<line number>:<content>`. Paths may be POSIX
   (`src/app.py`), Windows (`C:\repo\app.py`) or network (`\\server\share\app.py`).
   - A path has no spaces and contains `/`, `\` or `.`. So the log timestamp
     `2026-10-03 09:00:01` is **not** a grep line (version 2, S8a SCR-003).
   - Version 1 grouped such timestamps under fake `[file]` headers; the first evaluation found
     it.
   - The price is that `Makefile:3:` and paths with spaces are not grouped. They stay as they
     are.
2. It runs only if the segment has at least 5 grep lines in total (not per file).
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

**Settings.** `compressors.search_group.enabled`, `min_group_lines` (5),
`apply_to_verbatim_tools` (off: switch it on to group search output that comes through `Bash`,
which is where most of it is in Claude Code).

**Evaluation.** Smoke, 2026-10-04, version 2: no measurable damage. The model found the right
`<path>:<line>` and copied the exact matched line in 22 of 22 cases each, without the indentation
of the grouped form.

**Risks.** Tools that expect `path:line:` on every line would see a different format. The smoke
cases used the `Grep` tool. Whether agents copy grouped `Bash` output into edits correctly is
experiment E8 (S8b). It stays off by default: its saving is small (§12) and it changes what the
model reads.

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

**Before any code: refusals.** Removing the content of old tool results drew provider
refusals in 65–80 % of calls on `claude-opus-5-5` (E10(d), TOKLI_EVIDENCE §2). This pruner
removes outdated reads, so it must first pass the same refusal experiment.

**Open points for S8a-3** (S8a review M1, A1, A2):
- **A weak re-read must never supersede.** Claude Code answers a re-read of an unchanged file
  with a short "unchanged" message instead of the file, and errors carry no content either. A
  later read therefore has to be a real view, at least half the size of the old one, and not an
  error. Otherwise the only copy of the file would be stubbed.
- **The age counts on the old result.**
- **A "user turn" is a human message**, not a message that only carries tool results.

**On real traffic,** reads superseded under these rules are about 1.7 % of the tool-result
volume (§12).

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
   - The note is the last line. It ends with `\r\n` when every line of the log does, otherwise
     with `\n`.
   - If nothing would be omitted, the compressor does not apply.

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

**Settings.** `compressors.log_filter.enabled`, `debug_sample` (10), `apply_to_verbatim_tools`
(off: switch it on to filter logs printed through `Bash` or read with `Read`).

**Evaluation.** Smoke, 2026-10-04: no measurable damage. The model found the error code of the
failed request and copied the full error line exactly in 22 of 22 cases each. The test logs are
built to be very repetitive, so their saving (about 80 %) says nothing about real logs; see §12.

---

## 10a. `edit_args_on_resume` (selective, S8c)

**In one sentence.** When you come back to a conversation after a long pause, the full text of
old `Write` and `Edit` calls is replaced by a one-line note; the file paths stay.

**Problem.** Agents send back everything they wrote: the whole content of every `Write` and both
strings of every `Edit`, on every turn. On real Claude Code traffic these arguments are about a
third of the resent content (§12).

After a pause of more than an hour, the provider has forgotten its cache, and the whole
conversation is paid for again at the cache-write price. That is the moment when removing old
content costs nothing extra.

**How it works.**
1. **Conversation:** Tokli recognises the conversation by a hash of its first message and its
   system prompt. In memory only, it keeps the time of the conversation's last request and which
   calls it pruned.
2. **Resume:** a request is a **resume** when the conversation was last seen more than an hour
   ago (`pruning.resume_after_s`), or is new to Tokli, for example after a restart.
3. **At a resume:** every `Write`/`Edit`/`MultiEdit` call followed by at least 4 of your messages
   (`pruning.resume_min_age_turns`) has its long strings replaced: `content`, `old_string`,
   `new_string`. Messages that only carry tool results do not count as yours.
4. **Until the next resume:** exactly the same replacements are applied to every following
   request, so the provider cache stays valid. No newly old call is pruned before the next pause.

**Example**

```text
turn 1   Write config.py   content: <3,000 tokens of the file>
...      (six of your messages, then a two-hour pause)
```
Forwarded after the pause:
```text
turn 1   Write config.py   content: [tokli: earlier edit content omitted (3000 tokens) — read the file for its current state]
```

**Proven (the retention rule).**
- The structure, ids, `file_path` and every other argument stay unchanged.
- Between two resumes the forwarded beginning of the conversation is byte for byte the same.
- Nothing is pruned outside a resume, and nothing younger than the age limit.

**Not proven, so selective.** The text the agent wrote is gone from the conversation. To use it
again, the agent must read the file.

**Assumed.** Hours later, the agent does not need the exact text it wrote, and reads the file
when it does (`edit_content_not_needed`). Experiment E10(a) showed both parts on
`claude-opus-5-5`:
- the provider accepts the changed history;
- asked for a value, the model read the file instead of guessing.

**Settings.** `compressors.edit_args_on_resume.enabled` (off), `pruning.resume_after_s` (3600),
`pruning.resume_min_age_turns` (4), `pruning.resume_min_tokens` (64),
`pruning.resume_edit_fields`, `pruning.conversation_states` (1024).

**Evaluation: damage detected; do not switch it on.**
- On `claude-opus-5-5` the provider **refused** far more often once the assistant's own old
  `Write` arguments had been changed:
  - in the smoke run, 26 % of calls against 9 % with the original history;
  - in E10(c), every form of stub tried raised the refusals, including an empty string.
- When the model did answer, it was right (it read the file). The refusals alone make the pruner
  unusable on this model.
- **Replacing tool results is not affected:** `duplicate_tool_results` drew no refusal in 132
  calls.

**Risks.**
- **A guess of "resume" while the cache is still warm costs one cache write.** For example when
  Tokli restarted a few minutes ago.
- **A re-read costs a tool call.** The dogfood week measures both with exact provider usage.

## 10. What Tokli deliberately does not do (v1)

| Idea | Why not |
|---|---|
| Deleting "unimportant" words from prose (articles, connectives) | Corrupts code, for example identifiers named `a` or `the`, and indentation (TOKLI_EVIDENCE H01) |
| Re-formatting JSON by parsing and re-printing it | Changes numbers, escapes and duplicate keys (H09) |
| Dropping `null` or empty fields from JSON | Absent and `null` mean different things |
| Turning JSON arrays into tables | Types become ambiguous |
| Stripping comments from source code | Agents quote code back exactly (H04) |
| Removing whole tool calls, or shortening their arguments other than by `edit_args_on_resume` | Protocol pairing rules and provider validation (H07, H08). `edit_args_on_resume` (§10a) is the one exception, after E10(a). |
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
  was used up. It is visible so that a useful but slow compressor is never hidden. A skip is
  remembered with the cached results and repeated on later requests, so that timing never
  changes history already sent (which would cost a provider cache rewrite). Pruners and
  results already cached are never skipped.
- **Does not apply to your traffic** (S8h) marks an enabled compressor that almost never acts on
  what your agent sends, with the main reason in plain words, for example "the results are not
  JSON". `/tokli/health` lists such compressors in its `applicability` check, for information
  only.
- **Money saved** (S6) prices each compressor's saving by where it sat in the provider's cache:
  - at the cache-read price when it was in the cached history;
  - at the cache-write price when it was in the part written that turn;
  - at the input price when uncached.

  It is an estimate with a range. On a subscription it reads "value at API prices".
- Each figure carries its method: **exact** (from the provider), **calibrated**, or **estimate**.

## 12. What the compressors save on real Claude Code traffic (measured 2026-10-04)

The source is the developer's own Claude Code sessions of 14 days (39 sessions, about 17,800
requests), analysed locally with consent: counters only, no content. Details and method:
TOKLI_EVIDENCE.md §2 (E5b-lite, the cost map, the pruning simulation).

**Where the money goes** (provider usage, typical price ratios):

| Item | Share of cost |
|---|---|
| Cache reads (resent context, 0.1× the input price) | 64 % |
| Cache writes (context written to the cache, 1.25×) | 27.5 % |
| Output | 8.4 % |
| Uncached input | about 0 % |

76 % of the cache writes, about a fifth of all cost, happen when a session is resumed after more
than an hour: the provider cache has expired and the whole context is written again.

**What the built compressors save,** as a share of the tool-result volume, with "Also on Read,
Bash…" switched on:

| Compressor | Saving |
|---|---|
| `search_group` | 0.51 % |
| `log_filter` | 0.83 % |
| both | 1.34 % (under 0.2 % with the default verbatim list) |

`Bash` and `Read` carry 84 % of the tool-result volume, but most of it is source code and varied
command output that no safe transformation shrinks. Because nearly all of it is paid at the
cache-read price, the effect on cost is well under 1 %.

**Where the volume is:**
- **Tool-call arguments: about 46 % of the resent content,** more than all tool results (about
  41 %). They are the contents written by `Write` (22 %), `Bash` commands (12 %) and `Edit`
  strings (10 %).
- **Inside `Bash` output:**
  - about a third is reading files through `sed`, `cat` and `grep`;
  - 11 % is test-runner output.

**The lever that would matter** is pruning old history at the moment the context is rewritten
anyway after a pause.
- **Estimated saving:** 6 % of total cost when pruning only old `Write`/`Edit` contents, and
  about 10 % when also pruning old tool results. This is an offline cost estimate, not a measure
  of model behaviour.
- **It is now `edit_args_on_resume` (§10a, S8c),** off by default. Its first part is the old
  `Write`/`Edit` arguments, estimated at about 6 % of cost, and the dogfood week measures what it
  really saves.

