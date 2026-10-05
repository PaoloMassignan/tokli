# AGENTS.md — How coding agents work on Tokli

This file is for any coding agent other than Claude Code (for example OpenAI Codex).

**The rules in `CLAUDE.md` apply to you in full.** Wherever `CLAUDE.md` says "Claude", read
"the agent". This file only adds what an agent new to the repository needs. If the two seem to
disagree, `CLAUDE.md` wins; ask the human.

## 1. Before anything else

1. Read `CLAUDE.md`, then the brief of the slice you were given (`slices/S<n>/BRIEF.md` when one
   exists), then the specs and documents it names.
2. **Work only on the slice you were asked for.** Never start the next one.
3. **Gates are the human's.** At every gate, stop and wait. Explicit approval means words such
   as "approved", "approvo" or "go ahead with S<n>". Silence, a question back or approval of
   another gate is not approval.

## 2. Talking to the human

- The human writes in Italian. **Answer in Italian.**
- **Every file you write is in English:** code, comments, tests, docs, slice documents and
  commit messages.
- Be short and concrete. Report results as they are: a skipped step is reported as skipped, and
  a failing test with its output.

## 3. Setting up and running the checks

Python 3.11–3.13. No network access is needed by the test suite.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: . .venv/bin/activate
pip install -e ".[dev,ui-test]"
python -m playwright install chromium

pytest                                   # full suite (browser tests skipped)
RUN_BROWSER_TESTS=1 pytest tests/ui      # dashboard tests in headless Chromium
ruff check . && ruff format --check .
mypy                                     # strict, on src/
lint-imports                             # architecture contracts (TOKLI_ARCHITECTURE §5)
```

- On Windows PowerShell, set the variable with `$env:RUN_BROWSER_TESTS = "1"`.
- **CI** runs the suite on Windows, Linux and macOS × Python 3.11–3.13
  (`.github/workflows/`). Code that only works on one OS is a defect.

## 4. Hard rules (summary of `CLAUDE.md`; read the full text)

- **Specs first.** A spec is never changed to make code pass. A wrong requirement goes through
  a Spec Change Request (`CLAUDE.md` §4), and you stop.
- **Tests:**
  - tests first;
  - never weaken, skip, `xfail` or delete a test to make it pass;
  - test only real components in-process; only the upstream network is faked.
- **Privacy:**
  - never print, log or commit credentials or prompt content;
  - fixtures are synthetic;
  - no personal paths or usernames in the repository (a contract test scans for them).
- **Self-contained specification:** no document, code, test or commit message names an earlier
  project (`CLAUDE.md` §8).
- **Ask first:**
  - anything that costs money or uses real credentials;
  - reading real data on the developer's machine;
  - deleting data;
  - **commits and pushes**: commit only when the human asks, on the slice branch, never on
    `main` directly;
  - never push branches named `archive/*`.
- **YAGNI:** no infrastructure for later slices; no new dependency without an ADR
  (`CLAUDE.md` §6).
