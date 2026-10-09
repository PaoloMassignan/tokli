# S8h SCR-002 — `PowerShell` is a verbatim tool by default

Status: **approved 2026-10-09** ("metti powershell"). Found by the shape count of S8h P2.

## 1. Affected requirements

- **SPEC 017:** the default of `compression.verbatim_tools`, which is `["Read", "Bash", "shell",
  "shell_command", "container.exec"]`.
- **CC-021** uses that list. It is unchanged.

## 2. Evidence (counters only, the human's sessions, 21 days, 2026-10-09)

- **Claude Code on Windows uses a `PowerShell` tool**, with inputs `{command, description}`
  (sometimes `timeout`, `run_in_background`): 381 results with string output, like `Bash`.
- **It is not in the default list,** so compressors without the opt-in apply to it.
- **An agent copies its output back, exactly as it does `Bash` output.** For example, it quotes
  a file shown with `Get-Content` into an `Edit`. This is the hazard `verbatim_tools` exists for
  (H04).

## 3. Proposed change

- **New default:** `compression.verbatim_tools` defaults to
  `["Read", "Bash", "PowerShell", "shell", "shell_command", "container.exec"]`.
- **No other change.** A user can still override the list.

## 4. Impact

- **Tests:** the default-configuration table and `config_hash`, and the doctor goldens.
- **Compatibility:**
  - `config_hash` changes;
  - non-reference compressors no longer touch `PowerShell` results, unless their opt-in is on;
  - no schema or key changes.
