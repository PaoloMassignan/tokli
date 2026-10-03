# ADR 0011 — Request transformation off the event loop

Status: accepted (S4.5, 2026-10-03; approved at S4.5 Gate 1) · Related: SPEC 002 PX-006, PX-010, PX-015;
SPEC 009 CC-008, CC-024; SPEC 008 TM-004; ADR 0002, ADR 0009

## Context

The proxy runs on one asyncio event loop (ADR 0002). Up to S4, `parse`, `pipeline.run` and
`render` of a transformable request run synchronously inside the async handler. That work is
bounded by `compression.request_budget_ms` per request only after the fact (CC-008: calls are not
preempted), and parsing a body near `limits.max_transform_bytes` adds to it. While it runs, the
loop relays nothing: the SSE streams of every other request in flight stall. AC-PX-3 holds for
one request, but not across requests. PX-015 (S4.5) makes this a requirement.

The whole-request estimate (TM-004) already runs in a worker thread, so the token counters are
already used from more than one thread (`TokenCounter` holds a lock around its cache).

## Decision

- `ProxyHandler` runs the transformation (content-encoding and size checks, parse, pipeline,
  render, and their trace spans) in one call on a worker thread through
  `anyio.to_thread.run_sync`, for every transformable request. One path for every size: no size
  threshold to tune.
- The handler awaits that call, then opens the upstream request. The request keeps the service
  snapshot it read at its start (CF-005, ADR 0009).
- Fail to pass-through (PX-010) is unchanged: the worker function catches the same exceptions as
  today and returns the original bytes.
- Shared state touched from worker threads:
  - `ResultCache` (CC-024) gets a `threading.Lock` around `get` and `put` (lookup, LRU move,
    insertion and eviction). Compressors run outside the lock.
  - `TokenCounter` is already thread-safe.
  - Pipeline stages, the engine settings and the registry are immutable after construction. Per
    request state (stats, invocations, `Trace`, `_State`) is owned by the one request.
- anyio's default thread limiter (40 tokens) bounds concurrent transformations. No new setting.
- A client disconnect during the transformation is handled as today: the worker call is not
  interrupted (anyio does not abandon a running thread call), and the disconnect is seen by the
  relay (PX-009). The handler's cancellation behaviour does not change.

## Alternatives considered

- **A size threshold** (offload only large bodies): two code paths and a new tuning constant; the
  pipeline time does not follow body size closely (pruning depends on the duplicates).
- **A process pool**: preempts runaway compressors, but every request pays serialisation of the
  canonical request, and the result cache and token counters would be per process. Kept for a
  future `cost_class: expensive` compressor (CC-008).
- **Leave it as is and document the limit**: the human chose to fix it in S4.5 (P2 = a).

## Consequences

- Tests: AC-PX-8 (causal, no timing threshold); a concurrency test of `ResultCache`; the
  existing AC-CC-13 cache tests and all proxy tests stay unchanged.
- Performance: each transformable request pays one thread hand-off. E9 overhead is re-measured
  and compared with the S4 baseline (`benchmarks/baseline/`), reported, not gated.
- Observability: span names and meanings unchanged; `ms_tokli_overhead` keeps its definition and
  now includes the hand-off.
- Portability: no OS-specific behaviour; worker threads are already used on every platform.
- Migration: none (no persisted format, config key or API changes).
