# Getting started with Tokli

Tokli is a small proxy that runs on your own computer, between Claude Code and Anthropic. It
shortens what Claude Code sends, without losing information. A dashboard shows what it saved,
in tokens and in money.

- **Today it works with Claude Code and the Anthropic API**, with an API key or a Claude Pro/Max
  subscription. OpenAI and Codex come later.
- **Nothing leaves your computer except the requests Claude Code was going to send anyway.**
  Tokli stores only metadata (sizes, timings, which compressor saved what), never the text of
  your conversations.

## 1. Install

You need **Python 3.11, 3.12 or 3.13**; newer versions are not supported yet. On Windows the
`py` launcher picks the version.

```sh
# Windows
py -3.12 -m pip install --user pipx
py -3.12 -m pipx install "git+https://github.com/PaoloMassignan/tokli@v0.1.0"

# macOS / Linux
python3.12 -m pip install --user pipx
python3.12 -m pipx install "git+https://github.com/PaoloMassignan/tokli@v0.1.0"
```

If `tokli` is not found afterwards, run `py -3.12 -m pipx ensurepath` (or `python3.12 -m pipx
ensurepath`) and open a new terminal.

## 2. First-time setup

```sh
tokli setup tokenizers    # downloads the token-counting files once, and checks them
tokli doctor              # must end with "Result: all checks passed"
```

## 3. Connect Claude Code

Start Tokli and leave the terminal open:

```sh
tokli serve
```

Point Claude Code at it. For every session, add this to your Claude Code user settings:
`%USERPROFILE%\.claude\settings.json` on Windows, `~/.claude/settings.json` on macOS and Linux.

```json
{
  "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787/anthropic" }
}
```

If the file already has an `"env"` block, add the line to it.

**To try it for one session only:**
- PowerShell: `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/anthropic"`
- macOS/Linux: `export ANTHROPIC_BASE_URL=http://127.0.0.1:8787/anthropic`

Then start `claude` in the same terminal.

**Important: while this setting is on, Tokli must be running.** If it is not, Claude Code cannot
connect. Either start `tokli serve`, or remove the setting to go direct again.

## 4. Every day

1. Start `tokli serve`.
2. Use Claude Code as usual.
3. Open the dashboard at **http://127.0.0.1:8787/tokli/**:
   - **Overview:** what was saved, in tokens and money.
     - Money is an estimate with a range, priced by where each saved token sat in Anthropic's
       cache.
     - On a subscription it shows the value at API prices, not money you were billed.
   - **Compressors:** what each one saved.
   - **Recent requests:** one line per request, with its details.
   - **Settings:** switch compressors on or off. A change applies to the next request.

## 5. What is on by default

Only compressors that keep all the information are switched on:

| Compressor | What it does |
|---|---|
| `json_minify` | Removes JSON whitespace. |
| `duplicate_tool_results` | Sends an identical earlier tool result as a short reference. |
| `reread_by_reference` | Sends a file read again after an edit as its changed lines plus references to the earlier read. |

The others are off. `TOKLI_COMPRESSORS.md` explains each one, with examples.

**One cache rewrite after a change.** Switching compressors on or off changes how the history is
sent. Anthropic then rewrites its cache once on the next request, which costs a little extra.
Prefer changing settings between tasks, not in the middle of one.

## 6. Where things are

| What | Windows | macOS | Linux |
|---|---|---|---|
| Optional config file `tokli.yaml` | `%APPDATA%\Tokli` | `~/Library/Application Support/Tokli` | `~/.config/tokli` |
| Data: metadata database `tokli.db`, tokenizer files | `%LOCALAPPDATA%\Tokli` | `~/Library/Application Support/Tokli` | `~/.local/share/tokli` |

- **Records are kept for 30 days by default.** The setting is on the Settings page.
- **Your own prices** (for example a negotiated rate) can go in `price-book.yaml` in the data
  folder, in the same format as the shipped one (`src/tokli/pricing/price_book.yaml`).
- **To see the effective configuration:** `tokli config show`.

## 7. If something goes wrong

| Symptom | What to do |
|---|---|
| Claude Code says it cannot connect | `tokli serve` is not running, or runs on another port. Start it, or remove `ANTHROPIC_BASE_URL`. |
| `port 8787 … already in use` | `tokli serve --port 8788`, and use `:8788` in `ANTHROPIC_BASE_URL`. |
| `tokli doctor` reports a failed check | Each failed check prints its cause and a fix. |
| You suspect Tokli changes Claude Code's behaviour | Press **Lossless only**, or switch compressors off on the Settings page. To compare without Tokli, remove `ANTHROPIC_BASE_URL`. |

## 8. Update and uninstall

```sh
py -3.12 -m pipx install --force "git+https://github.com/PaoloMassignan/tokli@<new tag>"
py -3.12 -m pipx uninstall tokli
```

- **After an update:** the first request may rewrite Anthropic's cache once, as after a settings
  change.
- **After uninstalling:** delete the data folder (§6) to remove the metadata as well.
