# S8i SCR-002 — Erratum: AC-PR-17's one-hour boundary

Status: **approved** (2026-10-16, "yes" (translated from Italian)); applied to SPEC 019 AC-PR-17.

## 1. Affected requirement and acceptance criterion

- SPEC 019 AC-PR-17 (approved for S8i, 2026-10-16). PR-021 itself is unchanged.

## 2. Evidence

- **PR-021:** a resume when the conversation "was last seen **more than** its cache lifetime plus
  `pruning.resume_margin_s` seconds ago". With a 1 h lifetime and a 60 s margin, that is more
  than 3,660 s.
- **AC-PR-17, 1 h case:** "3,660 s later → a resume; 3,659 s later → not". At exactly 3,660 s the
  pause is not *more than* 3,660 s, so PR-021 says "not a resume".
- **AC-PR-17, 5 min case:** "361 s later → a resume; 360 s later → not". This one agrees with
  PR-021 (300 + 60 = 360).
- The S8c code and AC-PR-11 also use "more than" (`since > resume_after_s`).

## 3. Why the criterion should change

The two halves of AC-PR-17 apply different boundaries, and only one of them matches PR-021. A
test cannot satisfy both PR-021 and the 1 h half as written.

## 4. Proposed change

> **AC-PR-17** (PR-021, PR-027): the previous request carried `ttl: "1h"`; 3,661 s later → a
> resume; 3,660 s later → not. The previous request carried markers without `ttl`; 361 s later →
> a resume; 360 s later → not.

## 5. Impact on tests

`test_resume_uses_previous_request_ttl_1h` asserts 3,661 s → resume and 3,660 s → not. No other
test changes.

## 6. Impact on architecture

None.

## 7. Compatibility and migration

None. Behaviour differs from the written AC only at one exact second.
