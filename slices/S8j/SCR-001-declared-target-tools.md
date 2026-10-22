# S8j SCR-001 — A compressor that declares its target tools bypasses the verbatim filter

Status: **approved** with S8j Gate 1 (2026-10-22). It follows the human's answer to the
S8j review P3 (one switch), confirmed on 2026-10-22.

## 1. Affected requirements and acceptance criteria

| Spec | Requirement | Change |
|---|---|---|
| SPEC 009 | CC-021 (approved; changed by S8a SCR-001) | new exception (c) |

No existing acceptance criterion changes. SPEC 019 AC-PR-32 covers the new exception.

## 2. Evidence

- **What CC-021 says today:** every non-reference compressor skips the results of
  `verbatim_tools` (`Read`, `Bash`, `PowerShell` and the Codex shell tools by default), unless its
  `apply_to_verbatim_tools` option is set.
- **What `outline_first_read` needs:** it acts only on the results of `Read`, `Bash` and
  `PowerShell`. Under CC-021 as written, switching it on would take two switches, and its main
  switch alone would do nothing.

## 3. Why the current requirement should change

- **The CC-021 opt-in was designed for general compressors,** such as `search_group` and
  `log_filter`, which work on any tool and may also work on verbatim ones.
- **A compressor whose whole purpose is those tools** needs no second switch. It is already
  SELECTIVE and off by default, so the user's one switch is the explicit consent.

## 4. Proposed change (exact new EARS text)

> **CC-021** THE engine SHALL apply the `verbatim_tools` filter to every compressor except:
> - (a) those with equivalence `reference`, because a reference stub leaves the original bytes
>   verbatim in the target segment, and such compressors SHALL declare the assumption
>   `quotes_from_reference_target`;
> - (b) a compressor whose option `compressors.<id>.apply_to_verbatim_tools` is true. That
>   option SHALL default to false, SHALL exist only for compressors that declare it, and SHALL
>   NOT be true by default for any compressor;
> - (c) a SELECTIVE compressor that is off by default and declares `target_tools`, for the
>   results of exactly those tools.
>
> (S8a SCR-001, S8j SCR-001.)

## 5. Impact on tests

- **New:** `test_outline_applies_to_declared_verbatim_tools` (AC-PR-32), and a contract test
  that the registry rejects `target_tools` on a LOSSLESS or default-on compressor.
- **Unchanged:** the CC-021 tests for (a) and (b).

## 6. Impact on architecture

- `CompressorSpec` gains an optional `target_tools`, and the engine's verbatim filter reads it.
- **No new dependency direction,** no persistence change.

## 7. Compatibility and migration

None. No existing compressor declares `target_tools`, so the effective behaviour of every current
configuration is unchanged. `config_hash` changes only through the new S8j keys.
