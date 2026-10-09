# Tokli

**Tokli makes coding agents cheaper to run, and shows you by how much.**

Tokli is a small proxy that runs on your own computer, between Claude Code and Anthropic. It
shortens what Claude Code sends, keeping all the information, and a local dashboard shows what
it saved: in tokens, and in money priced the way Anthropic really charges, cache included.

- **Nothing to change in how you work.** You point Claude Code at Tokli once, and keep working.
- **Safe by default.** Only compressors that keep every piece of information are switched on.
  The others are opt-in, each with the evaluation behind it.
- **Honest numbers.** Every figure says how it was obtained (counted by the provider, calibrated,
  or estimated). Money comes with a range and, on a subscription, is labelled as value at API
  prices.
- **Private.** Everything stays on your computer. Tokli stores sizes and timings, never the text
  of your conversations.

**What to expect.** In long sessions most of the history is already in Anthropic's cache, where
it costs little, so savings on that part are modest. The dashboard shows your own figure, priced
after the cache.

## Quick start

You need Python 3.11–3.14 and Claude Code (with an API key or a Pro/Max subscription).

```sh
py -3.12 -m pip install --user pipx                  # macOS/Linux: python3.12 -m pip …
py -3.12 -m pipx install "git+https://github.com/PaoloMassignan/tokli@v0.1.1"
tokli setup tokenizers
tokli serve
```

Then add this to `~/.claude/settings.json` (on Windows `%USERPROFILE%\.claude\settings.json`):

```json
{ "env": { "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787/anthropic" } }
```

Use Claude Code as usual, and open the dashboard at **http://127.0.0.1:8787/tokli/**.

The full guide covers every step, the defaults, the files and troubleshooting:
[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).

## Status

**Version 0.1.1.** It works with Claude Code and the Anthropic API. OpenAI and Codex support is
planned (`TOKLI_ROADMAP.md`). How each compressor works, with examples, is explained in
`TOKLI_COMPRESSORS.md`.

## How it is built

Tokli is developed specification-first and test-first, with human approval at every step: the
behaviour is specified and approved before any code exists, and every requirement is traced to
its tests. Method, documents and development setup: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Licence

Apache-2.0.
