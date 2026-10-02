# SCR-001 — Measurement sizes for the linear-time checks

Slice: S1 · Status: **approved 2026-10-02** (product owner: "approvo SCR-001") · Raised: 2026-10-02

## Affected requirements and acceptance criteria

- **AC-RT-1** (SPEC 011): "for inputs of 0.5 MB and 5 MB the time ratio is ≤ 15".
- **CP-JM-005** test note (SPEC 010): "time ratio for inputs of 10× size stays ≤ 15×", applied in
  the test to 2,000 vs 20,000 JSON items (about 0.2 MB vs 2 MB).

## Evidence

CI run 37037209028, job windows-latest / Python 3.11:

```text
FAILED tests/unit/test_pipeline.py::test_features_linear_time
assert (0.004455 / 0.000277) <= 15        → ratio 16.1
```

The same test passed in the other 8 jobs, and locally in every run. Earlier runs showed ratios of
19–20 for a previous version of the test that measured segment count instead of length.

## Why the current criterion should not stay as written

The code is linear: it uses `str.strip`, a single pass, and an O(n) counter. The ratio exceeds 15
because **0.5 MB fits in the CPU cache and 5 MB does not**. The larger input pays memory latency
that the smaller one does not. That makes a correct, linear implementation fail intermittently on
shared CI runners. A quadratic implementation would show a ratio of about 100, so the check is
meant to separate ~10 from ~100, not to measure cache behaviour.

## Proposed change

- **AC-RT-1:** "feature extraction time grows linearly: for inputs of **5 MB and 50 MB** the time
  ratio, best of 3 runs each, is ≤ 15 (correctness constraint, every commit)."
- **CP-JM-005 test note:** "time ratio for inputs of **5 MB and 50 MB**, best of 3, stays ≤ 15."

Both sizes are then larger than any CPU cache, so both measurements are memory-bound and the ratio
reflects the algorithm. The threshold of 15 is unchanged.

## Impact on tests

`test_features_linear_time` and `test_json_minify_linear_time` change their input sizes. Each run
takes about 0.1–0.3 s longer and uses at most about 150 MB of memory temporarily. No other test is
affected.

## Impact on architecture

None.

## Compatibility and migration

None: test-only change, no persisted format, config key or API involved.

## Outcome after approval (2026-10-02)

- **Applied:** SPEC 011 AC-RT-1 and the SPEC 010 test note now say 5 MB and 50 MB, best of 3. Both
  status lines record "Changed by SCR-001".
- **The impact estimate above was wrong.** With the 50 MB input, `test_json_minify_linear_time` took
  about 20 s, not 0.1–0.3 s more. The cause was not the test: the string-literal regex of
  `json_minify` processed about 8–10 MB/s, because it used an alternation per character. It was
  replaced by the equivalent "unrolled loop" form, `"[^"\\]*(?:\\.[^"\\]*)*"`, which is about 20 %
  faster on many short strings and about 5× faster on long strings. The output is identical,
  guarded by `prop_json_minify_decode_roundtrip`. The test now takes about 4 s;
  `test_features_linear_time` takes about 0.3 s.
- The test input uses ~1 KB JSON items with one long string each. The sizes are as approved.
