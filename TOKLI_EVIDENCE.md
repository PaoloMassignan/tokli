# TOKLI — Evidence base

This document holds the facts that the Tokli specification relies on as **rationale**: known
failure modes of token-reducing proxies (hazards) and the measurements that shaped the roadmap.
Each hazard is described so that it can be understood, and reproduced, without any other
document. Requirements cite these ids in `TOKLI_TRACEABILITY.md` ("Why" column).

Evidence strength: **[REPRODUCED]** = demonstrated by running a transformation on a crafted input ·
**[OBSERVED]** = seen in real proxy traffic or logs · **[DESIGN]** = follows from protocol or
system properties.

## 1. Hazards

### Compression correctness

| Id | Hazard | Strength | Tokli controls |
|---|---|---|---|
| H01 | **Word-deletion "prose compression" corrupts code.** Deleting articles and connectives removes identifiers such as `a`, `an`, `the` from source code, and collapsing whitespace destroys indentation. | [REPRODUCED] | not in v1 (TOKLI_SCOPE deferred); CC-002, CC-015 |
| H02 | **"Lossless" as a label, not a property.** Transformations described as lossless silently dropped lines, reordered lines across groups, removed blank lines or normalised whitespace. Only a decoder plus a property test proves preservation. | [REPRODUCED] | CC-001, CC-002, CC-015, CC-016 |
| H03 | **Search-output grouping loses data.** A grouper that recognises only POSIX paths drops `C:\…:12:` lines (Windows) and `--` separators, and discards lines it cannot parse. | [REPRODUCED] | CP-SG-002, CP-SG-003 |
| H04 | **Verbatim-quoting hazard.** Agents copy tool output back byte-exactly: edit anchors (`old_string`), JSON arguments, line-numbered file dumps. Any transformation of such output, even a lossless one, can make the next tool call fail. | [OBSERVED] | CM-006, AN-003, CP-JM-004, CC-021, E8, E11 |
| H05 | **Rewriting already-sent history breaks prompt caching.** Providers cache request prefixes. Changing an earlier message (e.g. eliding the *earlier* copy of a duplicate) makes the next request re-write the cache (more expensive than a cache read). | [DESIGN] | CM-001, CC-006, CC-018, PR-004, PR-009, TC-004 |
| H06 | **Flattening corrupts conversations.** Joining a conversation into one string, compressing it, and writing it back into a single slot duplicated and corrupted content. | [OBSERVED] | CM-002 |
| H07 | **Reordering or merging blocks breaks protocol rules.** Moving text before `tool_result` blocks, rebuilding user messages or merging same-role messages can violate tool-use pairing and role rules. | [DESIGN] | CM-004, AN-004, PR-005 |
| H08 | **Structural removal needs atomicity knowledge.** Removing tool-call/result pairs requires protocol-specific rules (e.g. reasoning items that must stay with their calls). | [DESIGN] | PR-005, E10 |
| H09 | **Parse-and-dump changes JSON.** Re-serialising JSON changes number spelling (`1.0` → `1`), escapes (`é` ↔ `\u00e9`), and duplicate-key handling. | [REPRODUCED] | CP-JM-002, CM-011 |
| H10 | **Diff detectors swallow trailing text.** A diff trimmer that treats every line after a hunk as diff content removed user text that followed a diff. | [OBSERVED] | CP-DT-002 |
| H11 | **Structural detectors fire on look-alike text.** Markdown or YAML lists look like diffs, and prose with `path:12:` looks like grep output. | [REPRODUCED] | RT-001, CP-DT-004 |
| H12 | **Routing on markers or optional models is unstable.** Choosing a strategy from benchmark prompt markers, or from a learned model that may be missing on a machine, makes behaviour depend on the dataset and the machine. | [OBSERVED] | RT-005, CF-007, PT-001 |
| H13 | **Strategy dispatch by conditionals.** A central `if strategy == …` chain with per-strategy error handling makes compressors inconsistent (different fallbacks and guards) and unattributable. | [DESIGN] | CC-001, CC-009, CC-011 |
| H14 | **Silent identity on failure.** Compressors that catch every exception and return the input unchanged, with no record, hide defects. | [OBSERVED] | CC-008, CC-010 |

### Measurement and cost

| Id | Hazard | Strength | Tokli controls |
|---|---|---|---|
| H20 | **One tokenizer for every model, provider usage ignored.** Savings computed with a mismatched tokenizer and never checked against provider-reported usage are unverifiable. | [OBSERVED] | TM-001, TM-003, TM-005, AN-005 |
| H21 | **Mismatched measurement bases.** Comparing a whole-body baseline with a compressed-scope figure (or the reverse) inflated or deflated savings. | [OBSERVED] | TM-004, TM-005, TC-003 |
| H22 | **Flat-price cost.** "Tokens × one input price" ignores cache reads (≈ 10 % of the input price) and cache writes (≈ 125 %). For agent traffic that is mostly cache reads, it overstates savings by up to 10×. | [DESIGN] | TC-004, TC-006, TC-008 |
| H23 | **Evaluation pitfalls.** Metrics that normalise away what a compressor removes (token F1 ignoring articles); one case per category; harnesses that bypass the real pipeline; quality functions returning a constant. | [OBSERVED] | QE-001, QE-003, QE-004, QE-007, TC-005 |

### Proxy, protocol and privacy

| Id | Hazard | Strength | Tokli controls |
|---|---|---|---|
| H30 | **Changed upstream errors.** Turning provider 4xx into 500, or dropping response headers, breaks client retry and error handling. | [OBSERVED] | PX-005, PX-007 |
| H31 | **Buffered or silent streams.** Buffering a stream breaks interactive clients. Errors inside a stream were invisible in logs. | [OBSERVED] | PX-006, OB-006 |
| H32 | **Guessing the provider.** Defaulting unknown paths to one provider sends traffic to the wrong place. | [OBSERVED] | PX-002 |
| H33 | **Limits the provider does not impose.** Rejecting large bodies (e.g. > 10 MB) breaks valid requests. | [OBSERVED] | CM-012, PX-011 |
| H34 | **Credential and content leakage.** Logging credential prefixes or prompt previews (thousands of characters per request) leaks secrets and code. | [OBSERVED] | SC-005, UP-006, OB-007, OB-008 |
| H35 | **Client keys refused.** A proxy that accepts only its own gateway keys cannot serve a client that brings its own provider key. | [OBSERVED] | UP-002 |
| H36 | **Implicit credential discovery.** Searching many locations and inherited environment variables for keys makes behaviour differ per machine and can send the wrong key. | [OBSERVED] | UP-005 |
| H37 | **Key files with BOM or UTF-16.** Files written by Windows tools produced invalid headers. | [OBSERVED] | UP-007 |
| H38 | **Mixed responsibilities.** Security filtering, knowledge features and compression in one request handler made each hard to test and to disable. Hand-ordered stages had ordering rules only in comments, and timing and error handling were copied per stage. | [OBSERVED] | SC-001, PL-001, PL-002, PL-005 |
| H39 | **Structure injected into requests.** Adding tools (e.g. retrieval of compressed content) or cache breakpoints changes what the client asked for. | [DESIGN] | SC-003 |
| H40 | **Unprotected admin endpoints.** A mutating local endpoint without Origin/Host checks can be triggered by any web page. | [DESIGN] | API-006 |
| H41 | **UI that needs a build step.** Missing built assets silently removed the dashboard. | [OBSERVED] | UI-006 |

Machine-dependence hazards (working directory, environment precedence, network at start-up,
paths, line endings, encodings, Python versions) are listed with their controls in
`specs/018-portability-and-diagnostics` (MD-01…MD-28).

## 2. Measurements

### E5a — real agent traffic, counters only (2026-09-28)

Method: offline aggregation of counters and boolean flags from the logs of a local compression
proxy that had been used for real Claude Code work. Prompt text was dropped on load, and no
content was read or stored. Token figures are local `cl100k` estimates, not provider usage.

| Finding | Value |
|---|---|
| Text compression saving on real work (323 requests, 2 days) | **8.1 %** of the compressed scope (p10/p50/p90 per request: 3.0 / 7.1 / 12.9 %). Almost all of it came from transformations that Tokli classifies as lossy or selective (H01, H02, H03). |
| Tool-history pruning on the same work (70 requests) | **38.9 %** of whole-body tokens (3.43 M of 8.82 M). Pruned tool pairs: Edit 3,166 · Read 1,490 · Write 725. Relevance was chosen by a knowledge model that Tokli excludes, so this is an **upper reference**, not a prediction. |
| Repetition pattern | **75 %** of pruned entries touched a file that was touched again in the same request. |
| Exact-duplicate elimination (lossless part) | 157,871 tokens, about 1.1 % of the compressed scope. It removed the earlier copy, which is cache-hostile (H05). |
| Compression latency | average **1,071 ms** per request (max 1,474 ms), against 2,078 ms average provider latency. Whole-conversation compression added roughly 50 % to request latency. |
| Composition question | Not answerable from the flags available (they are per-request unions over the resent history). E5b measures it with Tokli's own analyzers. |

Limits: one real workspace, two days, one developer.

Consequences in the specification: tool-history pruning is in v1 (SPEC 019); LOSSLESS ONLY should
expect low single-digit text-compression savings (risk R3 in docs/DEVELOPMENT.md); latency is a real product risk
(CC-014, E9, TOKLI_TEST_STRATEGY §8).

### E5b-lite — composition, cost and saving on real Claude Code sessions (2026-10-03/04)

**Method:**
- **Data:** the session files of the developer's own Claude Code work over 14 days: 39 sessions,
  about 17,800 requests, 28 context compactions. Subagent side-chains were left out.
- **Analysis:** local scripts with the developer's consent. Only counters and flags are kept and
  printed; no text, path or tool argument is printed or stored.
- **Measures:**
  - provider usage is exact, from the session files;
  - content tokens are estimated as characters / 4;
  - "weighted" = a content's tokens × the number of later requests that resend it, stopping at
    the next compaction;
  - costs use typical relative prices: input 1, cache write 1.25, cache read 0.1, output 5.

**Where the cost goes** (exact usage):

| Item | Tokens | Share of cost |
|---|---|---|
| Cache reads | 7.58 B | 64.0 % |
| Cache writes | 261 M | 27.5 % |
| Output | 19.9 M | 8.4 % |
| Uncached input | 0.37 M | about 0 % |

**Cache writes come from full rewrites.**
- 88 % of cache-write tokens come from requests that rewrote most of the cached context (579
  requests).
- 76 % of all cache writes follow a pause of more than an hour since the previous request. Only
  5.7 % follow a pause of 5 to 60 minutes.
- This is consistent with a one-hour provider cache lifetime.

**Resent content,** by part, weighted (estimate). The session files do not hold the system prompt
or the tool definitions.

| Part | Share |
|---|---|
| `Write` arguments (file contents) | 21.7 % |
| `Bash` results | 19.5 % |
| `Read` results | 15.3 % |
| `Bash` arguments (commands and inline scripts) | 12.2 % |
| `Edit` arguments | 9.7 % |
| User and assistant text | 11.8 % |
| Other | 9.8 % |

**Tool results only:**
- `Bash` 47 % and `Read` 37 % of their volume.
- **Shapes:**
  - grep-shaped results are about 6 %;
  - log-shaped results about 6 %;
  - JSON-shaped about 1 %;
  - diffs 0.4 %.
- **Inside `Bash`:**
  - about a third is reading files with `sed`, `cat` and `grep`;
  - 11 % is test-runner output.
- **Long results:** the part of results above 4,000 tokens beyond their first and last 2,000
  tokens is 1.7 % of the resent content.
- **Superseded reads:** reads superseded by a later full view (a real view of at least half the
  size, not an error, at least four human turns old) are 1.7 % of the tool-result volume.

**Measured saving of the built compressors,** default options, run offline over the same tool
results:

| Setting | `search_group` v2 | `log_filter` | Both |
|---|---|---|---|
| Opt-in for `Bash`/`Read` on | 0.51 % | 0.83 % | 1.34 % |
| Default (`Bash`/`Read` excluded) | — | — | under 0.2 % |

The figures are shares of the tool-result volume. Version 1 of `search_group` measured 0.74 %,
because it grouped log timestamps as paths (S8a SCR-003).

**Simulation: pruning old history only when the context is rewritten anyway.**
- **When:** at the requests that the provider usage shows as full rewrites after a pause.
- **What:** items older than K human turns are replaced by a 20-token stub, and they stay
  replaced afterwards, so the cache prefix stays stable.
- **Saving per request:** 1.25 × the removed tokens at rewrites, and 0.1 × in the other turns,
  until compaction or the end of the session.

| What is pruned | K = 4 | K = 10 |
|---|---|---|
| Old `Write`/`Edit` arguments | 5.9 % of total cost | 4.3 % |
| + superseded reads | 6.1 % | 4.4 % |
| + every old tool result above 500 tokens | 10.5 % | 7.6 % |

The pause threshold (more than 1 hour, or more than 5 minutes) changes the figures by less than
0.2 points.

**Limits:**
- one developer, 14 days;
- content tokens are estimates;
- the simulation measures cost only, not model behaviour, and not extra calls the model might
  make after pruning (for example re-reading files).

**Consequences in the specification:**
- The lossless, prefix-stable compressors save well under 1 % of cost on this traffic, because
  nearly all resent tokens are paid at the cache-read price.
- The large levers are:
  - tool-call arguments (E10);
  - pruning at the moments when the cache is rewritten anyway.

  Both need conversation state and time, which SPEC 009 CC-006 currently excludes.

### E10(a) — the provider accepts stubbed edit arguments (2026-10-04)

**Method:** `evals/experiments/e10a_api_acceptance.py`, run by the developer on `claude-opus-5-5`,
4 calls; the result is in `evals/experiments/e10a_result.json`.
- **The conversation** (synthetic): the agent writes `config.py`, edits it, has four unrelated
  exchanges, and is asked for a value from the file.
- **The two variants:** the history as sent, and the history with the `content`, `old_string` and
  `new_string` of the old calls replaced by Tokli's stub.

| Variant | HTTP status | Model behaviour (2 of 2) |
|---|---|---|
| Original | 200 | Answers from the earlier `Write` content (`4`, correct) |
| Stubbed | 200 | Calls `Read` on `config.py` instead of answering from memory |

**Consequences:**
- The API accepts the stubbed history.
- The model behaves as the assumption `edit_content_not_needed` expects: it re-reads the file
  rather than guessing.
- The re-read is an extra call that the cost simulation above does not include. The S8c dogfood
  week measures it.
- The stub was about as long as this tiny file, so this run measures acceptance and behaviour,
  not saving.

### S8c smoke run — stubbed edit history draws refusals (2026-10-04)

**Run:** `tokli eval smoke --compressor edit_args_on_resume` on `claude-opus-5-5`, 22 synthetic
cases × 3 repetitions × 2 arms. Report:
`evals/results/2026-10-04-edit_args_on_resume-claude-opus-5-5/report.md`.

- **No wrong answer** in either arm.
- **Refusals** (`stop_reason: refusal`): 6 of 66 with the original history, **17 of 66** with
  the old `Write` content replaced by
  `[tokli: earlier edit content omitted (<n> tokens) — read the file for its current state]`.
- **Verdict:** `damage_detected` (b = 4, c = 0).

**Reading:**
- A provider-side refusal triggered by edited assistant history is a hazard of the same kind as
  H05/H07: a transformation that is valid for the protocol but changes how the provider treats
  the request.
- Two calls in E10(a) were too few to see it.

### E10(c) — any edit of the assistant's own tool-call history draws refusals (2026-10-04)

**Method:** `evals/experiments/e10c_stub_wording.py` on `claude-opus-5-5`; result in
`evals/experiments/e10c_result.json`.
- 10 synthetic cases of `reread_after_pruned_edit`, including the 5 refused in the S8c smoke run.
- 2 repetitions per case.
- Four forms of the old `Write` content.

| Form of the old `Write` content (20 calls each) | Correct | Wrong | Refused |
|---|---|---|---|
| Original (control) | 16 | 2 | 2 |
| `[tokli: earlier edit content omitted (<n> tokens) — read the file for its current state]` | 12 | 0 | 8 |
| `[tokli: <n> tokens omitted]` | 9 | 0 | 11 |
| Empty string | 12 | 3 | 5 |

**Reading:**
- The imperative wording is not the cause: the purely descriptive stub drew more refusals.
- Emptying the content also raised them.
- Changing the assistant's own past tool-call arguments, in any form tried, makes the provider
  refuse far more often.
- **Contrast:** replacing *tool results* (user-side content) drew no refusal in 132 calls (E11,
  `duplicate_tool_results`).

**Consequence:** pruning tool-call arguments (`edit_args_on_resume`, E10) is not viable on this
model. Pruning old tool results at a resume is the remaining form of the lever.

### E10(d) — removing an old tool result's content draws refusals too (2026-10-04)

**Method:** `evals/experiments/e10d_result_stubs.py` on `claude-opus-5-5`; result in
`evals/experiments/e10d_result.json`.
- **The conversation** (synthetic): the agent reads a settings file with `Read`, has five
  unrelated exchanges, and is asked for a value from the file.
- **Size:** 10 cases, 2 repetitions, four forms of the old result.

| Form of the old `Read` result (20 calls each) | Correct | Refused |
|---|---|---|
| Original (control) | 20 | 0 |
| `[tokli: earlier tool output omitted (<n> tokens)]` | 7 | 13 |
| The same + "— read the file again if you need it" | 7 | 13 |
| Empty string | 4 | 16 |

**Reading:**
- Replacing the content of an old tool result, with any stub or with nothing, made the provider
  refuse in 65–80 % of calls, against none with the original.
- The wording of the stub does not matter.
- `duplicate_tool_results` drew no refusal in 132 calls (E11). Its stub names an identical copy
  that is **still in the conversation**. A plausible reading, not proven: the decisive factor is
  whether the information stays available in the request.

**Consequence:** on this model, pruning that removes information from earlier turns is not
viable in the forms tried:
- edit arguments (E10(c));
- tool results (E10(d)).

The same caution applies to `superseded_tool_results` (S8a-3), which removes outdated reads.
Lossless-by-reference pruning stays sound.

### Repeated reads of source code, and E10(e) — a re-read by reference keeps edits exact (2026-10-04)

**How much read code is already in the conversation** (the developer's sessions, counters only):
- 22.5 % of the meaningful lines of `Read` results were already in the context window.
- Rebuilding each file from the conversation itself (the last full read, the agent's `Write`, and
  later `Edit` calls applied) and comparing line by line, the `Read` volume splits into:

  | Kind of read | Share of `Read` volume |
  |---|---|
  | First view, or not rebuildable | 83.7 % |
  | Identical to the last read with the edits applied | 10.4 % |
  | Identical to the agent's own `Write` | 2.3 % |
  | Identical to the last read, unchanged | 1.6 % |
  | Near or different | 1.8 % |

**E10(e):** `evals/experiments/e10e_reread_by_reference.py` on `claude-opus-5-5`; result in
`evals/experiments/e10e_result.json`.
- **The conversation** (synthetic): a module of about 250 lines is read, one function is edited
  (one line becomes two, so later line numbers shift), and the file is read again.
- **The task:** the agent must `Edit` a line in another, unchanged function. With the reference
  form, that line's exact text exists in full only in the first read.
- **Size:** 10 cases, 2 repetitions.

| Form of the second read (20 calls each) | Correct `Edit` | Wrong anchor | Refused | Mean request input tokens |
|---|---|---|---|---|
| Whole file (control) | 20 | 0 | 0 | 7,139 |
| Changed lines + `[tokli: lines a-b unchanged — identical to lines c-d of the read in call <id>]` | 20 | 0 | 0 | 4,106 |
| The same, each note also naming its functions | 20 | 0 | 0 | 4,195 |

**Reading:**
- A re-read that sends only the changed lines and refers to an earlier read for the rest kept
  every edit anchor exact.
- It drew no refusal and cut the request by 42 % in this setting.
- It agrees with E11, and contrasts with E10(c)/(d): the provider does not object when the
  information stays in the request.

### S8e smoke run — re-reads by reference cause no measurable damage (2026-10-04)

**Run:** `tokli eval smoke --compressor reread_by_reference` on `claude-opus-5-5`, 66 synthetic
cases × 3 repetitions × 2 arms (396 calls).

| Family | Assumption | n | b | c | Errors (base / cand.) | Verdict |
|---|---|---|---|---|---|---|
| `reread_fact_lookup` | `reads_partial_reference` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `reread_edit_anchor` | `quotes_from_reference_target` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `reference_verbatim_quote` | `quotes_from_reference_target` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |

- **No refusal and no error.** Exact input tokens fell from 1,055,835 to 629,031 (−40.4 %) on
  these cases.
- **Consequence:** the compressor is on by default (CC-020).

### E2 dry run — a later duplicate undid an earlier re-read (2026-10-05)

**Run:** `evals/experiments/e2_cache_economics.py`, dry run (the test suite runs it). An 8-turn
synthetic conversation went through two Tokli instances (compressors off and default) to a
simulated prompt cache.
- **The simulator:** it reads the longest prefix cached by an earlier request, writes up to the
  request's last breakpoint, and sends the rest uncached.
- **Units:** one token per UTF-8 byte of each block's JSON.

**Finding:** before the fix, the candidate arm's cached prefix stopped growing every second
request, and Tokli's predicted saving was about twice the observed one (relative error +0.98).
- **The cause:** a read identical to an earlier re-read was stubbed by
  `duplicate_tool_results`. That made the re-read a reference target, and CC-019 then rejected
  `reread_by_reference` on it.
- **The effect:** the re-read, sent as notes on the previous request, went whole on the next.
  History already sent changed, and the cache was rewritten from there.

**Fix (S6 SCR-001):**
- the earlier segment's change wins;
- the later stub is reverted and offered again to the pruners, so the second re-read also
  becomes notes.

**After the fix:** the candidate's cached prefix grows on every request, and the relative error
is +0.14, within the ±0.25 tolerance.
- **The residual is a unit effect of the simulator:** JSON escapes count as extra bytes there,
  not in Tokli's estimate. It places a little of the old saving in the written region.
- **The real run** against the provider, run by the human, measures the method in real tokens.

### E2 real run — the positional saving matches what the provider charges (2026-10-05)

**Run:** by the human; the result is in `evals/experiments/e2_result.json`.
- **Setup:** `claude-sonnet-5`, 12 turns, 2 arms, 24 calls, price book `2026-10-04.1`.
- **Input-side cost:** baseline $0.2890, candidate $0.1607. The observed saving is
  **$0.1283 (44 % of the input-side cost)** on this synthetic conversation.
- **Tokli's positional prediction:** $0.1537 (range $0.0582–$0.7066). Relative error
  **+0.198**, within ±0.25: **pass**.
- **Both runs overestimate slightly** (+0.14 dry, +0.20 real). A small part of the saving in old
  history is placed in the region written to cache, at the write price, where the provider
  read it from cache.
  - Cause: the region boundary is an estimate, scaled by `k`.
  - Effect: the dashboard figure leans high by about a fifth on this traffic. The range always
    contains the observed value.


### Other quantitative inputs

| Input | Value | Use |
|---|---|---|
| Pretty-printed JSON minification | 20–45 % of the JSON's tokens on typical API/MCP output (small samples) | expected-range sanity check for `json_minify`; real share unknown until E5b |
| Long-context dictionary substitution | 72–91 % task accuracy retained on long-context benchmarks (small n) | why `dictionary` stays off until E7 |
