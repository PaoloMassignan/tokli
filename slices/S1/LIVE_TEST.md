# S1 — Live test runbook (E1a API key, then E1b Pro/Max)

Run by the product owner. It uses real credentials, so Claude never runs it (`CLAUDE.md §3`).
Everything happens in **new PowerShell windows**. The variables are set only in the Claude Code
test window and disappear when it is closed. No other Claude Code session goes through Tokli.

Replace `<repo>` below with the folder where you cloned the repository (it contains `.venv`).

PowerShell does not run programs from the current folder unless you prefix them with `.\`. In
every window that runs Tokli, first define a shortcut and always call Tokli through it:

```powershell
$tokli = "<repo>\.venv\Scripts\tokli.exe"
```

## 0. Once: provision the tokenizer

```powershell
& $tokli setup tokenizers
& $tokli doctor
```

`doctor` must end with `Result: all checks passed`.

## 1. Window A: start Tokli

```powershell
$tokli = "<repo>\.venv\Scripts\tokli.exe"
& $tokli serve --log-format text
```

Expected: `Tokli … listening on http://127.0.0.1:8787/anthropic`. Leave the window open. It prints
one line per request: metadata only, never prompts or keys.

## 2. Window B: E1a with an API key

```powershell
New-Item -ItemType Directory -Force C:\temp\tokli-live-test | Out-Null
Set-Location C:\temp\tokli-live-test
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/anthropic"
$env:ANTHROPIC_API_KEY  = "<your API key>"
claude
```

If Claude Code asks whether to use the API key from the environment, answer yes. Then send these
three prompts, one at a time:

1. `What is 17 * 23? Answer with just the number.`
2. `Create hello.py that prints "hello from tokli", then run it with python and show me the output.`
3. `List the files in this folder and summarise what hello.py does.`

Pass condition: all three complete with no error shown by Claude Code. Window A shows one line per
request with `outcome=` and `status=200`.

Close window B when done (`/exit`, then close the window).

## 3. Window C: E1b with the Pro/Max login

Open a **new** PowerShell window, so no API key is set:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Set-Location C:\temp\tokli-live-test
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/anthropic"
claude
```

Send the same three prompts. Pass condition: the same as E1a. If Claude Code reports an
authentication error, stop and note the exact message. That is an E1b finding, and S1 still closes
on E1a.

## 4. Stop and report

- Stop Tokli with `Ctrl+C` in window A.
- Tell Claude which of E1a and E1b passed, and paste any error message.
- If you agree, Claude reads the telemetry database (`%LOCALAPPDATA%\Tokli\tokli.db`) to produce the
  completion-report figures: counts, outcomes, overhead percentiles, credential kind, header
  **names**. The database contains metadata only: no prompts, responses or keys.

## If something goes wrong

| Symptom | Meaning | What to do |
|---|---|---|
| `error: tokenizer o200k_base missing` | step 0 not done | run step 0 |
| `port 8787 … already in use` | another process uses the port | `tokli serve --port 8788` and use `:8788` in `ANTHROPIC_BASE_URL` |
| Claude Code cannot connect | Tokli is not running, or the URL is wrong | check window A; the URL ends with `/anthropic` |
| 404 `tokli_unknown_route` | Claude Code dropped the `/anthropic` path prefix (open question Q2) | stop and report: the fallback is a dedicated port per provider |
