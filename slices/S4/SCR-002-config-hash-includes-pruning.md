# S4 SCR-002 — `config_hash` includes the `pruning` section

Slice: S4 · Status: **approved 2026-10-03** ("Approvo scr 002"), applied to SPEC 017 · Date: 2026-10-03

## 1. Affected requirements

- **SPEC 017 CF-006** (approved for S0): "THE SYSTEM SHALL compute `config_hash` over the
  canonical JSON of behaviour-affecting keys (sections `compression`, `compressors`, `pipeline`,
  `tokens`, `limits`, where present), …".
- AC-CF-4 is unchanged.

## 2. Evidence

- S4 adds the section `pruning` (SPEC 017 "Keys added in S4"):
  - `pruning.duplicate_min_tokens`;
  - `pruning.duplicate_require_same_call`.
- Both change what `duplicate_tool_results` forwards, so they are behaviour-affecting, but the
  section is not in CF-006's list. As written, two requests with different pruning options would
  carry the same `config_hash`, and the dashboard's overhead groups and the eval provenance would
  mix them.

## 3. Why the current requirement should not be implemented as written

`config_hash` exists to tell apart requests forwarded under different behaviour. A list that
leaves out a behaviour section defeats that purpose for every pruning option.

## 4. Proposed change

CF-006: "… (sections `compression`, `compressors`, `pipeline`, `pruning`, `tokens`, `limits`, where
present) …".

## 5. Impact on tests

- `test_config_hash_stable_and_sensitive`: the default behaviour JSON gains the `pruning`
  section.
- New assertion: changing `pruning.duplicate_min_tokens` changes the hash.

## 6. Impact on architecture

None: `BEHAVIOUR_SECTIONS` gains one name.

## 7. Compatibility and migration

- **Default `config_hash`:** it changes once, in S4. It already changes in S4 because the
  section `compressors` gains `duplicate_tool_results`.
- **Persisted data:** records keep their hash.
- **Nothing to migrate.**
