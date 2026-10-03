# ADR 0008 — Evaluation package, layering and credentials

Status: accepted (S2.5, 2026-10-03; approved at S2.5 Gate 1, decisions P2, P3, P4) · Related:
SPEC 012, ADR 0004

## Context

S2.5 adds `tokli eval smoke`, the first code that calls a provider on its own initiative instead
of relaying a client's request. Three things must be settled:

- where the code sits in the layering;
- how it may authenticate, given that the proxy never holds credentials;
- what it writes to the repository.

## Decision

- **Package `tokli.eval`:** case loading and lint, checkers, runner, verdict, record and report.
  It sits in the same layer as `tokli.http`, as an **independent sibling**: the layers contract
  lists `tokli.http | tokli.eval`, so neither imports the other (AC-QE-4: no code path in
  `tokli.http` reaches evaluation). `tokli.cli` uses it; it uses `tokli.app` (bootstrap, so both
  arms run the same pipeline as `tokli serve`), the protocol adapter, the usage parser and the
  upstream client.
- **Credentials (QE-019):** an API key read only from the environment variable named by
  `--api-key-env`. It is sent as `x-api-key`, never read from configuration, and never stored,
  logged, printed or written to a result file. The proxy's passthrough rule is unchanged.
- **Paths:** the command takes `--evals-dir` explicitly. No working-directory-relative reads
  (portability rules).
- **Repository contents (QE-014, QE-016):**
  - committed: the case files (`evals/cases/`), the case generator (`evals/make_cases.py`), the
    records (`evals/records/`) and the summary reports (`evals/results/*/report.md`);
  - not committed (`.gitignore`): the per-case outputs (`cases.jsonl`).
- **Cost control (QE-018):** `--max-calls` is mandatory until a price book exists (S6). The
  plan is shown, then confirmation or `--yes`.

## Alternatives considered

- **Running the arms through a live `tokli serve`:** adds a server and telemetry rows to an
  offline tool. Rejected: the in-process pipeline is the same code (QE-001).
- **Reading `ANTHROPIC_API_KEY` implicitly:** convenient, but it breaks the rule that inherited
  provider variables are ignored unless configured. Rejected.

## Consequences

- One more import contract (the sibling layer).
- The self-test (QE-017) uses the real case files against a fake upstream, so it runs in CI
  without credentials.
