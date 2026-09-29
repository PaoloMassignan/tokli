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
expect low single-digit text-compression savings (README risk R3); latency is a real product risk
(CC-014, E9, TOKLI_TEST_STRATEGY §8).

### Other quantitative inputs

| Input | Value | Use |
|---|---|---|
| Pretty-printed JSON minification | 20–45 % of the JSON's tokens on typical API/MCP output (small samples) | expected-range sanity check for `json_minify`; real share unknown until E5b |
| Long-context dictionary substitution | 72–91 % task accuracy retained on long-context benchmarks (small n) | why `dictionary` stays off until E7 |
