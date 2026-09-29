# TOKLI — Vision

## One sentence

**Tokli is a local, transparent proxy that reduces the tokens and cost that coding agents send to
LLM providers, proves how much it saved and which compressor saved it, and never trades task
quality for a bigger number.**

## Who it is for

A developer or a small team running Claude Code, Codex or any OpenAI-/Anthropic-compatible client
on their own machine. They want to:

1. see what their agent traffic costs and how much of it is compressible,
2. switch on compression that *provably* keeps all information in the request (lossless), with its
   effect on real tasks measured rather than assumed, and
3. opt into more aggressive compression only with evidence that it does not hurt their work.

## Lessons it is built on

| Known failure of token-reducing proxies (TOKLI_EVIDENCE.md) | Tokli commits to |
|---|---|
| "Lossless" was a label. Compressors sold as lossless altered code. | **Lossless is a property proven by a decoder and a property test.** A compressor without a decoder is not lossless. Lossless means *information preserved*, not *identical model behaviour*: the latter is an assumption, declared per compressor and evaluated (SPEC 009, 012). |
| Savings were `tiktoken` estimates on a mismatched tokenizer, with several measurement bugs. | **Every number carries its method** (exact / calibrated / estimate). The provider's own `usage` is the reference whenever it is available. |
| One aggregate "saved %" figure. | **Per-compressor marginal attribution:** tokens, latency, acceptance rate, zero-benefit rate. You can tell which compressor is worth keeping. |
| Cost = tokens × one flat price. | **Pricing is a separate versioned table** that knows cache reads, cache writes and output. Where it cannot know, it says so. |
| Behaviour depended on files that happened to exist on a machine. | **Same explicit config + same input ⇒ same output on every supported machine**, checked in CI by a behavioural fingerprint. |
| Security, knowledge and compression grew into one handler. | **Token reduction only.** Clean seams let redaction or other stages be added later without touching adapters or compressors. |

## Principles

1. **Quality first.** Pass-through is always a correct answer. Compression is accepted only when
   it is permitted by policy, applicable, and strictly shrinking.
2. **Transparent.** Clients change only a base URL. Responses and streams are relayed byte-for-byte.
3. **Honest measurement.** No fabricated numbers. Unknown means "unavailable", not zero.
4. **Private by default.** Metadata, not prompts. Credentials are never logged.
5. **Small in functionality, strong in foundations.** Few compressors, well tested. Extensibility
   only where variability already exists: protocols, providers, compressors, policy, telemetry
   consumers.

## Success measures for v1

| Measure | Target | How it is measured |
|---|---|---|
| Compatibility | 0 client-visible protocol regressions on the compat corpus and in a 1-week dogfood | contract + compat tests; dogfood error log |
| Transparency | pass-through request ⇒ byte-identical upstream body; response/stream byte-identical | compat tests |
| Honest savings | every dashboard figure shows its method; exact forwarded tokens from provider usage when available | UI/API contract tests |
| Attribution | 100 % of forwarded token reduction attributed to named compressors | invariant test: Σ marginal = total saving |
| Overhead | **Product target**, not an architectural constraint: p95 Tokli overhead ≤ 25 ms for requests ≤ 200k tokens with the default LOSSLESS ONLY pipeline | measured from S1 (benchmark E9 + dogfood distribution per size bucket, TC-013). A miss triggers a review of the default pipeline. It never rejects a compressor automatically (TOKLI_TEST_STRATEGY §8). |
| Reproducibility | identical behavioural fingerprint on Windows, Linux, macOS CI | portability job |
| Quality | default-enabled compressors pass non-inferiority on the full Tokli eval suite (`specs/012`) at v1 release; before v1, every default passes the smoke tier | evaluation record per compressor (QE-016) |

The overhead figure is a target in the same sense: it is kept visible and measured, but no
compression technique is rejected because an early, unmeasured number said so.

Savings targets are deliberately **absent** from v1 success measures. The first job is to measure
real traffic truthfully (experiment E5). A savings target set before that would repeat a known
pattern: optimising a number instead of a product.
