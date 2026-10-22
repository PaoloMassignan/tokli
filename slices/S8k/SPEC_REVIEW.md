# S8k — Spec review

**Slice scope** (`TOKLI_ROADMAP.md`, S8k, requested 2026-10-22): measure which parts of the cached
context the cache cost belongs to. The result ranks the candidate levers (S8l keepalive, S8m edit
arguments at their first resend, and others) by their weighted share.

**Specs in scope:** none of `specs/` changes. S8k builds a measurement tool, like the real-traffic
replay (S8h P4). It changes no proxy behaviour, no persisted format and no configuration key.
The normative text is a new row in `TOKLI_TEST_STRATEGY.md` §2 and the E5 row in §7.

**Out of scope:**
- any compressor, and any change to the proxy;
- the keepalive simulation (S8l) and the edit-argument pruner (S8m);
- a composition view in the dashboard.

## What exists already

- **E5b-lite** (`TOKLI_EVIDENCE.md`, 2026-10-03/04, 14 days) measured the resent content by
  tool, weighted by later requests. It used characters / 4 and did not split code from other
  files. It states: "the session files do not hold the system prompt or the tool definitions".
- **A first pass for this slice** (2026-10-22, 7 days, scratch scripts, counters only, with the
  human's consent) gave, weighted by later re-reads:
  - reads of non-code files 23.0 %, write arguments on code files 16.8 %, other tool results
    16.0 %, write arguments on other files 14.3 %, other call arguments 11.0 %, reads of code files
    11.0 %, text 6.8 %;
  - no ranged read of a code file followed a whole read of the same file in its context: 59 %
    followed output that named the file, 27 % followed other ranges only.
- **The proxy's telemetry cannot answer the missing part.**
  - It stores no tokens by segment kind.
  - The default data directory's database holds 353 requests of the main model, the last one on
    2026-10-13, while the session files hold about 5,100 requests in the last 7 days. Most recent
    traffic did not go through this Tokli instance.

## 1. Ambiguities

- **A1. "Weighted by re-reads".** A block is resent by every later request of its context, until
  the next compaction. Proposed reading: one request per assistant message (consecutive assistant
  events of one turn are merged, as in `tools.replay`). The weight is the number of later
  requests in the same context. This is the E5b-lite method.
- **A2. "Code".** Proposed reading: a file whose extension has an outline rule
  (`pruning.outline_rules`, S8j), so the split matches what the skeleton could act on. Every other
  extension counts as "other files". Markdown is reported on its own line, because it is the
  largest single part in the first pass.

## 2. Contradictions

None found.

## 3. Missing behaviour

- **M1. The fixed part (system prompt and tool definitions).** It is read by every request, but no
  local source holds its text. Two ways to measure it:
  - **(a) from the session files' exact usage:** the first request of each context has
    `input + cache_read + cache_write` = fixed part + first message(s). The first messages are in
    the file, so their estimate is subtracted. Across contexts, the fixed part is about constant
    for one client version and one MCP setup. No proxy is needed;
  - **(b) from the proxy:** new telemetry columns with tokens by segment kind (`SYSTEM`,
    `TOOL_DESCRIPTION`). That is exact, but it needs schema v6 and an ADR, and the human's traffic
    would have to go through Tokli for some days first.
  This is product question P1.
- **M2. Cost weighting.** Re-read tokens are paid at the cache-read price (0.1×). The same block
  is written again at every full rewrite after a pause, at 2× for the one-hour cache. For S8l and
  S8m the split matters, so the tool reports both: re-read tokens, and rewrite tokens (the block's
  tokens × the number of later rewrites in its context, a rewrite being a request whose exact
  usage shows a cache write of most of the context, as in E5b-lite). This is product question P3.

## 4. Portability concerns

- Session files are read as UTF-8 with replacement, as in `tools.replay`.
- Paths in tool arguments may be Windows or POSIX: classification uses `normalise_path` (S8e)
  and the extension only.
- Nothing is written, and no path is printed.

## 5. Observability requirements

A measurement tool. It has no spans and no telemetry. The privacy rules of the replay apply:
- counters only;
- consent asked on every run (`--yes` for a run already consented);
- no text, path, command or argument printed.

## 6. Architectural risks

- **Location:** `tools/composition.py`, next to `tools/replay.py`, outside `src/`, so no import
  contract changes. It may import `tokli` (as the replay does) and the replay's session reader.
- **Reuse:** the session reader (`_contexts`) and the shell-read classifier
  (`classify_shell_read`, S8j). The first is made public in `tools/replay.py` (a rename inside
  `tools/`, no behaviour change). No new seam.

## 7. Product questions (for the human)

- **P1. How to measure the fixed part.**
  - **(a)** From the session files' exact usage (M1 a): immediate, no proxy change, and an
    estimate with a stated error (the subtracted first messages are estimated).
  - **(b)** New telemetry by segment kind (schema v6). It needs some days of traffic through
    Tokli.
  - **Recommended: (a).** (b) only if (a) shows the fixed part is large enough to be a lever.
- **P2. Tool or one-off scripts.** **Recommended: a tool in the repository** (`python -m
  tools.composition`), tested on a synthetic session file like the replay, so that S8m and later
  slices can measure the same way. The first-pass scratch scripts are not kept.
- **P3. Which measures the tool prints.**
  - **(a)** Re-read tokens only.
  - **(b)** Re-read tokens and rewrite tokens (M2), plus an estimated cost share with the price
    ratios of the one-hour cache (input 1, write 2, read 0.1).
  - **Recommended: (b).** The rewrite part is what S8l would save, and the read part is what a
    first-send compressor (S8m) would save.
- **P4. Window.** **Recommended:** `--days 7` by default, like the replay. The record in
  `TOKLI_EVIDENCE.md` uses 14 days, to compare with E5b-lite.

## 8. Implementation decisions (Claude)

- **Parts reported** (rows):
  - fixed part (P1);
  - user text, assistant text, thinking;
  - call arguments of the write tools, split into code / Markdown / other files;
  - other call arguments by tool;
  - results of file reads, split into code / Markdown / other files;
  - other tool results by tool;
  - results of the write tools.
- **Tokens:** the provisioned tokenizer through `bootstrap`, as the replay; provider usage is used
  as is.
- **A context** is the part of a session between compaction boundaries. Side-chains are left out,
  as in the replay.
- **Rewrites:** a request whose exact cache write is at least half of its total input.

## 9. Test plan

- **`test_composition_counts_parts`:** a synthetic session file (canary content, a `Write` of a
  `.py` file, a `Read` of a `.md` file, a `Bash` `cat` of a code file, a test run, text), with
  exact re-read weights per part.
- **`test_composition_weights_stop_at_compaction`:** a block before a compaction boundary is not
  counted after it.
- **`test_composition_fixed_part_from_usage`:** first requests with usage give the fixed part
  minus the estimated first message.
- **`test_composition_rewrites`:** a request with a full cache write counts as a rewrite for the
  earlier blocks of its context.
- **`test_composition_prints_counters_only`:** the canary, paths and commands never appear in the
  output.
- **`test_composition_asks_consent`:** without `--yes` and with "n", nothing is read.

## Gate 1 record

- **Date:** 2026-10-22.
- **The human's words:** "I approve" (translated from Italian), for P1–P4 as recommended.
- **Spec delta:** no file in `specs/` changes. `TOKLI_TEST_STRATEGY.md` §2 gets a row for
  `tools/composition.py`, and §7 updates the E5 row.
