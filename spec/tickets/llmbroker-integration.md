# Ticket: consume llmbroker's direct client and pool streaming

- **Status:** upstream feature delivered; echo-words side not started
- **Upstream repo:** `andgineer/llmbroker`
- **Consumers:** echo-words (`api` and `llmbroker` backends). news-recap can use the same.

## What llmbroker provides today

The single-model direct call this ticket originally asked for **exists in llmbroker** — with a
different shape than the one first proposed, and the difference matters for echo-words's config
model:

- **It is registry-based, not constructor-based.** `AsyncBroker.direct(name)` returns a client for
  one entry of the broker's own registry; the entry lives in the same `llms.toml` the pool is
  configured from, under `[[custom]]` with `pool = false` (direct-only). There is no
  `DirectClient(provider=..., model=..., api_key=...)` to hand credentials to.
- **Keys never pass through echo-words.** An entry names an env var (`api_key_ref`); llmbroker
  reads it at call time through its secrets layer. echo-words sets the variable and nothing else.
- **Streaming is on the direct client**: `async for delta in client.stream(prompt)`, plus
  `await client.ask(prompt)` for the whole reply. The blocking `Broker.direct(...)` has `ask()`
  only.
- **Errors** come from one hierarchy under `LLMRequestError` (`UnknownModelError`,
  `MissingKeyError`, `ProviderError` with `AuthError`/`RateLimitError` subclasses,
  `LLMTimeoutError`) — one taxonomy for both backends, as this ticket wanted.
- **There are no per-provider SDKs to import lazily.** llmbroker talks to every provider over one
  httpx client against OpenAI-compatible endpoints, so the footprint concern behind the original
  "lazy per-provider import" requirement does not exist. Importing `llmbroker` lazily still makes
  sense so a broken install degrades to a config error, but it buys nothing dependency-wise.

## What is pending upstream

Tracked in llmbroker's `specs/plans/add-model.md`. echo-words should not design around these until
they land, but must not write assumptions that contradict them either:

- **Stable model aliases.** A `[[custom]]` entry gains an `alias` (`opus`) that survives version
  changes, while its `name` carries the exact version; `direct("opus")` follows whatever the
  curated catalog currently recommends, and `llmbroker preset … --merge llms.toml` refreshes the
  pinned model ids. This is what lets echo-words name a paid model once and never touch it again
  when the provider ships a new generation.
- **`direct()` becomes custom-only.** Reaching a preset pool model by name will raise; the pool is
  addressed only through `ask`/`chat`/`stream`. echo-words already uses the pool that way.
- **Pool streaming.** `AsyncBroker.stream(...)` will route with failover up to the first delta and
  stream from there, so the free pool stops being a single-chunk backend. Every place in the
  implementation plan that calls llmbroker "non-streaming" is scoped to today's release.

## What echo-words must do

1. **`api_backend.py`** — a thin adapter over `broker.direct(<entry>)` + `.stream(...)`, sharing
   the one `AsyncBroker` instance with the pool backend instead of building its own client.
2. **Config** — the paid model is an entry in the file `ECHOWORDS_LLMBROKER_CONFIG` already points
   at, added with `llmbroker add-model --into llms.toml`. One echo-words variable names the entry;
   the provider, model id, base URL and key-variable name all live in the TOML. The key itself
   goes in the environment under whatever name `api_key_ref` gives.
3. **Daily cap** stays echo-words's concern (`ECHOWORDS_API_DAILY_CAP`, falling back to the pool),
   as originally scoped — llmbroker does no spend accounting.
4. **Error mapping** — translate the `LLMRequestError` tree onto the bridge's `AgentError` once,
   for both backends.

## Acceptance criteria

- The `api` backend streams incremental deltas into the M3 bridge through `direct(...).stream(...)`.
- Only one `AsyncBroker` exists per process, serving both the pool and the paid backend.
- No API key is read, stored, or passed by echo-words code — only the env var name is configured.
- Auth / rate-limit / timeout / provider failures reach the bridge as `AgentError`.
- With the paid entry absent from `llms.toml`, the `api` backend degrades to a clear config error.
- Tests mock the provider (no network), mirroring llmbroker's own test approach.
