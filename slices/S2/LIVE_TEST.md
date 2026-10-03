# S2 — Live test runbook (E4 Anthropic, roadmap exit)

Run by the product owner. It uses real credentials and costs a few cents, so Claude never runs it
(`CLAUDE.md §3`). Everything happens in **new PowerShell windows**; the variables are set only in
the test windows and disappear when they are closed.

Replace `<repo>` with the folder where you cloned the repository (it contains `.venv`). The
repository must be on the branch `s2-usage-calibration`.

```powershell
$tokli = "<repo>\.venv\Scripts\tokli.exe"
```

**Note on the database.** On its first start, this build migrates `%LOCALAPPDATA%\Tokli\tokli.db`
from schema v1 to v2 (one new column, nothing removed; ADR 0005). An S1 build will then refuse
that database as "newer". Nothing else changes.

## 1. Window A: start Tokli with the log file on

```powershell
$tokli = "<repo>\.venv\Scripts\tokli.exe"
& $tokli serve --log-format text --set observability.log_file=true
```

Leave it open. Each request prints one line, now with the provider usage (`exact`), `k` and the
saving with its method.

## 2. Window B: a short Claude Code session (streamed)

```powershell
Set-Location C:\temp\tokli-live-test
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/anthropic"
claude
```

Use the login you prefer (API key or Pro/Max; both worked in S1). Send:

1. `What is 17 * 23? Answer with just the number.`
2. `List the files in this folder and summarise what hello.py does.`

Pass condition: no error in Claude Code; window A shows `usage` with `source=provider` for the
`/v1/messages` lines. Close the window when done.

## 3. Window C: one non-streaming request with a JSON tool result (API key)

This request carries a pretty-printed JSON result from a non-verbatim tool, so `json_minify`
saves tokens and the saving can be calibrated live. Claude Code's own `Read` and `Bash` results
are never compressed, which is why step 2 saves almost nothing.

Use **PowerShell**, not the Command Prompt (`cmd`): a prompt like `C:\Users\you>` without `PS`
in front is `cmd`, where `$env:` does not exist. Type the key only in the terminal, never in a
chat. The `curl.exe` command is **one line**; paste it whole.

```powershell
$env:ANTHROPIC_API_KEY = "<your API key>"
curl.exe -s http://127.0.0.1:8787/anthropic/v1/messages -H "x-api-key: $env:ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" --data-binary "@<repo>\slices\S2\live_request.json"
```

Pass condition: a normal JSON answer from the model. Window A shows `outcome=compressed`, a
non-zero saving with `method calibrated` and a `k` between 0.5 and 2.0.

## 4. Stop and report

- Stop Tokli with `Ctrl+C` in window A.
- Tell Claude whether steps 2 and 3 passed, and paste any error message.
- If you agree, Claude reads **metadata only** from the database and the log file
  (`%LOCALAPPDATA%\Tokli\tokli.db`, `%LOCALAPPDATA%\Tokli\logs\tokli.log`): usage categories,
  `k`, savings, SSE event types and counts (E4), header **names**, overhead. Neither file contains
  prompts, responses or keys.

## What E4 records

For every streamed request the trace and log line list the SSE event types seen and how many of
each, and the usage values read from `message_start` and `message_delta`. That answers Q3 (are
input fields repeated in `message_delta`?) and confirms or corrects the fixtures in
`tests/compat/fixtures/anthropic_responses/`. A mid-stream `error` event cannot be triggered on
purpose; that case stays fixture-based (SPEC 003, Q3).
