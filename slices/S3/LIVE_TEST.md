# S3 — Live test runbook (dogfood check, roadmap exit)

Run by the product owner, at the end of the slice. The repository must be on the branch
`s3-metrics-dashboard`. Replace `<repo>` with the repository folder.

**Note on the database.** On its first start this build migrates `%LOCALAPPDATA%\Tokli\tokli.db`
to schema v3 (one column added, nothing removed; ADR 0007). An S2 build then refuses it as newer.

## 1. Start Tokli (PowerShell)

```powershell
$tokli = "<repo>\.venv\Scripts\tokli.exe"
& $tokli serve --log-format text
```

The startup lines include `dashboard: http://127.0.0.1:8787/tokli/`.

## 2. Use Claude Code through Tokli

In another PowerShell window:

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/anthropic"
claude
```

Work normally for a few minutes (any small task).

## 3. Open the dashboard

Open `http://127.0.0.1:8787/tokli/` in a browser and check that you can answer, from the page
alone:

1. **How much?** On Overview: original, forwarded and saved tokens, each with its method label
   (`exact`, `calibrated`, `estimate`, or `estimate · N % calibrated`), and the saving %. Money
   shows "—" with `no_price_book` until S6.
2. **Which compressor?** On Compressors: the compressor's kind ("lossless · structural"), its
   assumptions, how often it ran and what it saved.
3. **What happened to a request?** On Recent requests: click a row to see its trace.

Also try the page on a phone-sized window, and with the system in dark mode.

## 4. Report

Tell Claude what worked and what was unclear or wrong. Screenshots are welcome; they show only
metadata (no prompts, responses or keys).
