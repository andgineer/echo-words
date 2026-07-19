# Ticket: direct single-model streaming client in llmbroker

- **Status:** proposed
- **Created in:** `andgineer/wordgram` — **to be moved to `andgineer/llmbroker`**
- **Driving consumer:** wordgram (the paid `api` backend). Also useful to
  news-recap and future tools.

## Summary

Add to llmbroker a **direct client** that calls one explicitly named (paid)
model directly — **no pool, no failover, no quality-routing** — and
**supports streaming** (an async iterator of text deltas). It reuses
llmbroker's existing provider adapters and call mechanics, but is exposed as a
**distinct public surface**, not a flag on `AsyncBroker`.

## Motivation

A consumer sometimes needs a single, explicitly chosen frontier model for
quality — not the free pool. Putting that model *into* the pool is wrong
(established separately): the free models are enough for failover, and a paid
model is chosen precisely because you want *that* model, which is the opposite
of pooled failover. So the paid path must be a **direct, explicit call**.

Rather than have each consumer hand-roll a multi-provider streaming SDK layer,
llmbroker — which already owns "talking to LLM providers" — exposes that call
directly. For wordgram this collapses two of its three LLM backends (free pool
+ paid direct) behind **one dependency and one error taxonomy**; only the
marginal CLI coding-agent stays separate.

## Why this belongs in llmbroker (not in the consumer)

- **Reuse** across the author's projects (wordgram, news-recap, future tools) —
  write the provider/streaming plumbing once.
- **Shared provider adapters.** llmbroker already calls many providers for the
  pool; the direct client reuses those adapters and their credential handling,
  so the marginal cost is small.
- **One error taxonomy** for consumers (a single-model analog of
  `NoLLMAvailableError`, timeouts, provider errors) instead of a second,
  parallel set in each consumer.
- **Streaming and failover divide cleanly along this seam.** The pool is
  non-streaming *because* it has failover — you cannot cleanly switch models
  mid-stream after deltas have already been emitted. The direct client has
  **no failover**, so streaming is safe and natural there. The direct client
  is the streaming-capable counterpart the pool architecturally cannot be — a
  natural completion of llmbroker's remit, **not scope creep**.

## Scope

**In:**
- Direct call to one named model of a configured provider (Anthropic / OpenAI /
  Google to start — reuse whatever provider set the pool already supports).
- **Streaming**: an async iterator yielding text deltas. This is llmbroker's
  first streaming surface.
- A non-streaming convenience call too (parity with the pool's `ask`),
  returning the full text — optional but cheap.
- **Lazy per-provider import** so a consumer that configures only one provider
  pulls in only that provider's SDK (keeps the footprint small — matters for a
  1 GB micro instance).
- Errors consistent with the pool's types (single-model analog of
  `NoLLMAvailableError`, timeout, provider/auth failure).
- A per-call timeout.

**Out:**
- No pool, no failover, no quality-routing, no `record_quality` — there is no
  pool to route among.
- No new provider integrations beyond what the pool already supports (unless a
  provider is trivially available through the existing adapters).
- No spend accounting/caps — that is the **consumer's** concern (wordgram caps
  it with `WORDGRAM_API_DAILY_CAP` and falls back to the pool; see its plan).

## Proposed API (illustrative — the final shape is the author's call)

```python
from llmbroker import DirectClient  # name TBD

client = DirectClient(provider="anthropic", model="<frontier-model>", api_key=...)

# streaming
async for delta in client.stream(prompt):
    ...  # text delta

# non-streaming
reply = await client.ask(prompt)      # -> reply.text
```

Keep it a **separate class/namespace** from `AsyncBroker`, and make the docs
say plainly: *single model, no pool, no failover* — so llmbroker's "broker"
identity stays coherent.

## Acceptance criteria

- Streaming yields incremental text deltas for at least one provider; a
  consumer can render them live.
- The non-streaming call returns the full text.
- A consumer configuring one provider does **not** import the other providers'
  SDKs.
- Auth / rate-limit / timeout / provider failures surface via llmbroker's
  error types.
- **No behavioral change** to `AsyncBroker` (the pool).
- Tests use mocked providers (no real network), mirroring llmbroker's existing
  test approach.

## Consumers & follow-up

- **wordgram** — `api_backend.py` becomes a thin adapter over this direct
  client; the M2 `api` backend delegates to it and streams into the M3 bridge.
  wordgram's `spec/implementation-plan.md` has already been updated to assume
  this feature exists (backend seam, config vars, module layout, deployment
  profiles). Until it lands, wordgram's `api` backend degrades to a clear
  config error.
- **news-recap** — can use the same direct client for its paid/quality paths.
