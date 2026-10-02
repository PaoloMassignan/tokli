# ADR 0004 — Module dependency rules and the composition root (from S1)

Status: accepted (S1, 2026-09-30); reviewed and accepted by the product owner at S1 Gate 2 (2026-10-02) · Related: TOKLI_ARCHITECTURE.md §5, §8

## Context

ARCH §5 lists allowed and forbidden imports per module. Implementing S1 showed three places where
the list, read literally, does not describe a buildable system:

1. ARCH §8 puts object construction in `tokli.app.bootstrap()`, but §5 lets `tokli.app` import only
   telemetry, pricing, config, compression metadata, tokens and domain. A composition root must
   import what it builds (pipeline, protocol adapter settings, upstream, auth, stages).
2. §5 lets `tokli.http` import pipeline, protocols, upstream and auth directly, but with a
   composition root HTTP needs only the built services, plus the protocol adapter and upstream
   types for the request flow.
3. Header semantics (hop-by-hop, RFC 9110) are needed by both `tokli.auth` (request headers) and
   `tokli.upstream` (response headers), and §5 forbids either importing the other.

## Decision

The enforced rules (`pyproject.toml`, `lint-imports`, run in CI) are:

```text
layers:  tokli.cli > tokli.http > tokli.app > tokli.compressors > tokli.compression
         > (tokli.pipeline | tokli.protocols | tokli.upstream | tokli.auth | tokli.telemetry
            | tokli.observability | tokli.config | tokli.tokens)   — independent of each other
         > tokli.domain                                            — standard library only
forbidden: tokli.compression, tokli.compressors ↛ protocols, upstream, auth, http, telemetry,
           app, pipeline, config
forbidden: tokli.http ↛ tokli.compression, tokli.compressors, tokli.tokens   (direct imports)
exception: tokli.compression.registry → tokli.compressors.*   (CC-011 places the list there)
```

- `tokli.app.bootstrap` is the **composition root**: the only place that builds tokenizers, the
  engine, stages, the pipeline, the upstream client and the store.
- Header semantics shared by several leaf packages live in `tokli.domain.headers` (stdlib only).
- `tokli.http` imports `tokli.telemetry.records` for the record type it fills.

Every forbidden edge of ARCH §5 still holds: compression never sees protocols, providers, HTTP,
auth, pricing or storage; adapters never import each other; the UI (later) talks only to the API.

## Consequences

- ARCH §5's allowed-imports list is superseded by these contracts. ARCH §5 points here.
- The independence of the leaf packages is now enforced, which is stricter than ARCH §5.
