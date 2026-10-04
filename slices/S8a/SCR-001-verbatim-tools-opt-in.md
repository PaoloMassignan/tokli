# S8a SCR-001 — Per-compressor opt-in for verbatim tools; availability without Tier 2

Status: **approved 2026-10-03** at S8a-1 Gate 1 ("Accetto"); review answers P3, P6.

## 1. Affected requirements

- **SPEC 009 CC-021** (approved S4): the `verbatim_tools` filter applies to every compressor
  except those with equivalence `reference`.
- **SPEC 017 CF-009** (approved S4): the UI-editable keys are `compressors.<id>.enabled` and
  `telemetry.retention_days`.
- **TOKLI_TEST_STRATEGY §5**, the acceptance table, column "To be available (off by default)",
  row SELECTIVE / LOSSY: "Tier 2 run and published; drop CI upper bound ≤ 5 pp".

## 2. Evidence

E5b-lite (`SPEC_REVIEW.md` §10) measured the human's last 14 days of Claude Code traffic: 39
sessions, 17,607 requests, counters only. 84.5 % of the tool-result volume comes from `Bash` (47.3 %)
and `Read` (37.2 %), the default `verbatim_tools`. The grep-shaped and log-shaped output that
`search_group` and `log_filter` address comes mostly from `Bash`: 53.0 M and 50.1 M of 68.5 M and
68.3 M weighted tokens.

## 3. Why the current requirements should change

- **CC-021.** Under CC-021 a user cannot apply `search_group` or `log_filter` to `Bash` output
  except by removing `Bash` from `verbatim_tools`, which applies to every compressor. The list is
  a HEURISTIC protecting against the verbatim-quoting hazard (H04). It should stay the default for
  all compressors, but the user should be able to lift it for one compressor at a time, knowingly.
- **Test strategy §5.** The table contradicts CC-020 (approved S1): "Whether the user may enable a
  compressor SHALL NOT depend on evaluation records." Tier 2 needs two providers (QE-003), so it
  cannot exist before S8b.

## 4. Proposed change

**CC-021 (new text):**

> THE engine SHALL apply the `verbatim_tools` filter to every compressor except (a) those with
> equivalence `reference`, because a reference stub leaves the original bytes verbatim in the
> target segment, and such compressors SHALL declare the assumption `quotes_from_reference_target`;
> and (b) a compressor whose option `compressors.<id>.apply_to_verbatim_tools` is true. That option
> SHALL default to false, SHALL exist only for compressors that declare it, and SHALL NOT be true
> by default for any compressor. (S8a SCR-001.)

**CF-009 (new text):**

> THE configuration schema SHALL mark each key as `ui_editable` or not. v1 UI-editable keys:
> `compressors.<id>.enabled`, `compressors.<id>.apply_to_verbatim_tools` (where it exists),
> `telemetry.retention_days`. (S4 SCR-001: there is no policy key. S8a SCR-001: the verbatim
> opt-in.)

**New UI-012 (SPEC 016):**

> WHERE a compressor declares `apply_to_verbatim_tools`, THE Settings page SHALL show a second
> toggle "Also on Read, Bash…" (listing the effective `verbatim_tools`), off by default. Next to
> it, the page SHALL state: "These tools' output is often copied back exactly by the agent (for
> example as an edit anchor). Changing it can make the agent's next tool call fail."

**Test strategy §5**, the "To be available" cell for SELECTIVE / LOSSY:

> Tier 0 guarantees pass (CC-015). Before v1 a compressor may be available without an evaluation
> record (CC-020); the dashboard shows it as "not evaluated". At v1 release: Tier 2 run and
> published; drop CI upper bound ≤ 5 pp per category it applies to.

## 5. Impact on tests

New tests:
- `test_verbatim_opt_in_applies_compressor_to_verbatim_tool`;
- `test_verbatim_opt_in_defaults_off`;
- `test_verbatim_opt_in_only_for_declaring_compressors`;
- `test_ui_verbatim_opt_in_toggle` (browser);
- `test_patch_verbatim_opt_in`.

`test_verbatim_tools_exempt_only_reference_equivalence` keeps its assertion for the default.
Its name and docstring now cover the opt-in. No assertion is weakened.

## 6. Impact on architecture

The engine's verbatim filter reads one more per-compressor setting. The config schema gets one
optional field per declaring compressor. No new module or dependency direction.

## 7. Compatibility and migration

- **Config:** new keys only, all defaulting to the current behaviour.
- **Fingerprint:** the `compressors` section is hashed (CF-006), so the new keys with their
  defaults change the default `config_hash` once with the upgrade, as the `pruning` section did
  in S4 (SCR-002). *Correction found during GREEN:* the first version of this SCR said the hash
  would change only when a user sets a new key, which was wrong. CF-006 itself is unchanged.
- **Persisted schema and API:** no change to the persisted schema. The config API lists the new
  keys like any other.
