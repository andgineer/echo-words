# echo-words — Implementation Plan

Execution handoff for the `echo-words` project. Read
`functional-description.md` first — it is the source of truth for
*what* to build; this plan says *how*. Where the two disagree, the
functional description wins.

## Where the work happens

Repository: `github.com/andgineer/echo-words`. It already contains the
0.0.1 scaffold: hatchling packaging with the version in
`src/echo_words/__about__.py`, `src` layout, pytest, `uv.lock`,
CI workflow (`.github/workflows/ci.yml`, runs `uv sync --frozen` +
`uv run pytest tests/`), and a publish workflow triggered by `v*` semver
tags. Build on top of it; do not restructure the packaging.

Rules:

- Python 3.12+. All imports at module top level. English-only comments
  and docs.
- Every new module gets tests in the same commit. `uv run pytest` must be
  green after every milestone.
- No real network in tests — fake or mock every boundary (LLM, AnkiWeb
  sync, TTS engines, dictionary API). The web app is tested through the
  in-process test client, never a live server.
- The frontend is not covered by pytest. Its **non-trivial logic** — the
  offline resend queue and the SSE client's reconnect/refetch — gets
  vitest tests in `webapp/`, run by `inv test` alongside pytest; markup
  and styling are checked by hand per milestone.
- Update `uv.lock` when adding dependencies (`uv lock`); CI uses
  `--frozen`.
- **CI runs on Linux only** (`ubuntu-latest`, Python 3.12 and 3.13). The
  deployment target is an x86_64 Linux VM, and two of this project's
  dependencies are Linux-first: the `anki` pylib wheels the plan pins and
  Piper's phonemization stack. macOS is the author's dev box and is covered
  by running the suite there by hand; Windows is not a supported profile for
  either running or testing this app.
- Execute milestones strictly in order (M0 → M8); do not start a
  milestone until the previous one's tests are green. M7 is the one
  milestone split across two sessions — M7a then M7b, see its section. Each milestone
  ends with an explicit test list — implement those tests, plus whatever
  the code itself obviously requires.

## Upstream dependency: llmbroker

echo-words targets **llmbroker ≥ 1.5.2** — pin it in `pyproject.toml` and
`uv.lock`. Everything this plan needs is in that release's public API; the
changes echo-words once waited on (`journal-lookup-keys`, `rating-by-key`,
`routed-call-identity`) have all landed, and they landed in a **better shape
than the earlier plan assumed**, which is why the three call sites below are
written the way they are:

- **`stream()` returns a `StreamHandle`, not a bare async generator.** It is
  async-iterable (`async for delta in handle`), and it additionally *names the
  model that answered and rates the call*. **Closing it is the consumer's
  move** — `await handle.aclose()` hands the model's slot back — so the
  pipeline wraps it in `contextlib.aclosing` (or try/finally) rather than
  iterating an inline call, which matters whenever a stream is abandoned
  (backend error, client gone, shutdown).
- **Quality feedback (M2) needs no trace lookup.** `await
  handle.record_quality(score)` rates the call the handle came from — the
  model, the operation and the call id are already on it, so there is no
  journal read and no id to persist. Sequencing constraint: a streamed call
  becomes rateable only once its answer has ended (the handle raises
  `ValueError` before that), which is exactly where echo-words rates it — the
  card is parsed after the stream completes. The delayed form
  `broker.record_quality(score, trace_id=…)` remains available and takes
  exactly one of `call_id=` / `trace_id=`; echo-words does not need it.
- **`/api/status` (M7) reads `handle.llm_name`** — the model that answered,
  available from the first delta on, no journal read. Keep it in memory with
  the call's outcome and time.
- **The pin's floor is the cascade itself.** `wait` bounding queueing *and
  the whole answer* in provider time, and a 200 carrying no text at all
  counting as a failure the pool fails over rather than an answer handed on,
  are both behaviours of the pinned release. Below it `wait` stops binding at
  the first delta, which turns the step-up trigger into a first-token timeout
  and lets an empty completion through as a successful answer.

`trace_id` is still passed on every call, now purely for tracing/analytics
rather than as the rating key.

M2 starts with a one-line sanity check against the installed llmbroker that
`StreamHandle` carries `record_quality` and `llm_name`; a mismatch is a
dependency-pin problem to fix in `uv.lock`, not something to code around.

## Execution protocol (how to drive this plan)

The plan is executed **one milestone per working session**, in order
(M7's two halves are two such sessions). For every milestone the
executing agent must:

1. Read, in this order: `functional-description.md` (at minimum the
   sections the milestone touches), then this file's "Rules",
   "Technology choices", "Configuration", "Languages configuration",
   "Web app and API", "Word pipeline", and "The LLM contract" sections,
   then the milestone's own section — plus any section or decision doc
   the milestone explicitly names (e.g. "Deployment" for M6/M8).
2. Implement exactly the milestone's scope — code and its tests in the
   same commit(s). Do not pull in later milestones' work; the "Word
   pipeline" step numbers say which step belongs to which milestone.
3. Finish only when `uv run pytest`, `ruff check`, and — from M1 onward —
   `npm --prefix webapp test` are green.
4. Where this plan and the functional description disagree, the
   functional description wins — and the plan is corrected in the same
   commit.

Prompt template for the operator (one per milestone):

> Execute milestone M\<N\> from `spec/implementation-plan.md`, following
> its "Execution protocol" section: read the sections it lists, then
> implement exactly M\<N\>'s scope with its tests. On any conflict,
> `spec/functional-description.md` wins. Finish with `uv run pytest`,
> `ruff check`, and, from M1 onward, `npm --prefix webapp test` green,
> then commit.

## Technology choices (fixed)

| Concern | Choice |
|---|---|
| Web framework | **FastAPI + uvicorn**: JSON API, server-sent events (a `StreamingResponse` with `media_type="text/event-stream"` — no extra SSE dependency), and static files (`StaticFiles`) from one process. Binds `ECHOWORDS_HOST:ECHOWORDS_PORT` (default `127.0.0.1:8080`); **`tailscale serve` publishes that port as HTTPS inside the tailnet** — the backend itself never handles TLS or auth (decision record: `spec/decision-interface.md`) |
| Frontend | **Vue 3 + Vite + `vite-plugin-pwa`**, sources in `webapp/`, built into `_static/` (gitignored) and served by the backend — the same stack, layout and build wiring as `dinary`, whose PWA this one is modelled on (see "Reuse from dinary"). **No Pinia**: the whole client state is the selected language, the entry list and the resend queue, which plain `ref`/`reactive` in a few composables hold without ceremony — dinary needs a store layer for its catalog/review/queue cross-talk, this app does not. Its `vite.config.js` PWA strategy is copied rather than re-derived: `registerType: "autoUpdate"` + `skipWaiting` + `clientsClaim` so a deploy reaches the phone on the next reload, `globPatterns` precaching the hashed output, `navigateFallback: "index.html"` with `navigateFallbackDenylist: [/^\/api\//]`, and `runtimeCaching` pinning `/api/*` to `NetworkOnly` so an API response is never served from cache. Frontend tests use dinary's established stack: Vitest + Vue Test Utils + happy-dom, reported through Allure and run in CI. Test non-trivial client logic and user-visible component behavior; static markup alone may be checked by hand |
| HTTP client (dictionary pronunciation) | `httpx` (async) |
| Anki integration | **`anki` pylib, headless** (the non-GUI core of Anki as a PyPI package; manylinux x86_64 + aarch64 wheels). The backend maintains its own collection in `ECHOWORDS_DATA_DIR/anki/` and syncs to AnkiWeb via pylib's `sync_login` / `sync_collection` / `sync_media`. Pin the version (`anki==26.8.1`, verified on VM2) and upgrade deliberately — the API this project uses has been stable for years, but pylib is versioned with the app. The wheels need **glibc ≥ 2.35**, which VM2 meets exactly; an older base image would rule the package out entirely. No AnkiConnect, no Anki desktop, no GUI anywhere. Decision record: `spec/decision-spaced-repetition.md` |
| TTS (local) | Piper (`piper-tts`, ONNX voices, MIT) — local neural TTS with per-language voices, ~60–100 MB per voice, real time on Raspberry-Pi-class CPUs, so it runs on the 1 GB micro instance. English `en_US-lessac-medium`, German `de_DE-thorsten-medium`. **Serbian is settled: Piper has NO usable Serbian voice** — the only `sr_RS` dataset (`serbski_institut`) is actually **Lower Sorbian** (Sorbian Institute recordings miscatalogued under the Serbian locale) and must never be configured; Serbian's engine is edge-tts (decision record: `spec/decision-tts.md`). Configured voices downloaded at startup, pinned-URL + checksum mechanism (M6). Piper phonemizes via `espeak-ng` — an optional system dependency, documented in the README (M8) |
| TTS (online) | `edge-tts` (MS Edge neural voices, free online, outputs mp3, per-language voices) — the **primary** engine for Serbian (`sr-RS-SophieNeural` / `sr-RS-NicholasNeural`, near-commercial quality, both scripts; no usable local voice exists — see `spec/decision-tts.md`) and the last-resort fallback for every other language when the local engine fails. Its known flakiness (unofficial API, recurring 403 breakage) is acceptable in both roles: audio is generated once per word and stored in Anki media, so an outage only affects words added during it |
| mp3 encoding | `lameenc` (pure-wheel LAME bindings) to convert Piper's WAV output to mp3 — no ffmpeg system dependency |
| Dictionary pronunciation | `https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}` where `{lang}` is the source language's `dict_api` code (`en`, `de`, …; Serbian is unsupported → skip this step) — take the first `phonetics[].audio` non-empty URL (they are Wiktionary recordings); for English prefer entries whose URL contains the configured accent (`-us` / `-uk`), else any |
| Settings | `pydantic-settings`, env prefix `ECHOWORDS_`, `.env` support |
| Durable state | **None of its own — no database.** The Anki collection is the only thing worth keeping and it is already a file that syncs to AnkiWeb. History is an in-memory ring buffer of recent entries; "added" statistics are counted from the collection itself (Anki note ids are creation timestamps in milliseconds, so a per-deck `find_notes` gives today / 7 days / all time without any side table); duplicate and lookup-only counters, undo state and correction state are in-memory and reset on restart. This removes `sqlite3`, a schema, migrations, and any need to back the app up |
| LLM | One **cascade** behind a single `stream_completion` seam (M2), not a per-language choice: every request goes to the free pool first and steps up to the paid model only when the pool misses the budget. Both steps are plain streaming text→text HTTPS calls through the author's `llmbroker` (`github.com/andgineer/llmbroker`, **≥1.5.2**), and one `AsyncBroker` instance serves both with one error taxonomy (`LLMRequestError` and its subclasses); it is created in the FastAPI lifespan (after the languages config) and `aclose()`d on shutdown. **Step 1 — the pool:** `broker.stream(prompt, operation=f"{prefix}-{lang}", wait=…)` returns a `StreamHandle`: async-iterable over text deltas, carrying `llm_name` (who answered) and `record_quality(score)`, closed by the consumer with `aclose()`. `wait` bounds **queueing plus the whole answer**, counted in provider time — the consumer's own pace is disarmed across every delta — so it is the single trigger for the step-up: set it at the **low end** of the functional description's ~20–30 s complete-answer budget — low enough that the pool's slow entries are cut before their first token, so a miss carries no half-answer to the user — and let the failure hand the request on. echo-words keeps no clock of its own and never measures the first token: a model that opens at once and then takes a minute misses that budget exactly like one that says nothing at all, which is the point of bounding the answer instead of its opening. **Step 2 — the paid direct client** (opt-in by configuration, never required): a single explicitly named frontier model, no pool, no failover, no routing. The model is **declared in echo-words's own code** at broker construction (`AsyncBroker(direct=[…])`) and reached with `await broker.direct(alias)`, which returns an `AsyncDirectClient` whose `.stream(prompt, timeout=…)` is a plain async iterator of deltas. That client borrows the broker's single shared httpx client, so obtaining one per request is cheap and echo-words must **not** close it. The alias comes from llmbroker's curated paid catalog and is an eternal handle — llmbroker re-points it at the current model generation on its own daily clock, so a provider's new release changes nothing here. Nothing is stored anywhere: the declaration in code is the only source of truth, and the API key is read at call time from the env var the catalog names, never touched by echo-words. The same client serves the user's explicit deeper-analysis request (M7). With no paid alias configured, or the daily cap spent, the cascade is one step long and a pool miss is a failure. The **M0 spike** measured both steps — see `spec/decision-llm-backend.md` |
| Lint | `ruff` (line-length 100), run in CI after tests |

## Reuse from dinary

`../dinary` is the author's expense-tracker PWA already running in
production **on the sibling of the instance echo-words will use** —
the same Oracle Free Tier shape in the same tenancy
(`spec/decision-deployment.md`) — reached over Tailscale, on the same
backend stack (FastAPI + uvicorn + pydantic-settings + llmbroker). It is a working precedent, not a
reference design: prefer copying its solved parts to re-deriving them,
except where this app's smaller footprint says otherwise (no store
layer, no database, and the frontend build stays off the server).

**Take:**

- **The PWA shell and its design system.** `webapp/src/assets/base.css`
  (dark-theme CSS custom properties), the component idioms, and the
  Vite + `vite-plugin-pwa` build wiring including `build.outDir:
  "../_static"` and the dev-server `/api` proxy. The workbox strategy
  above is the part hardest to get right by hand. Not its store layer:
  echo-words carries no Pinia.
- **Client composables that map 1:1 onto this app's needs**:
  `useOnline`, `swHealth` (network-failure reporting), `useStaleCache`,
  `useKeyboardVisible` (the iOS on-screen-keyboard offset — an
  input-first app needs it), the `_request.js` fetch wrapper with its
  error normalization, and the **`flushQueue` pattern** for the
  offline resend queue (M8). echo-words's queue is a plain reduction of
  it: one word per item, and no store layer to reconcile.
- **The whole deploy approach** — `invoke` tasks over ssh (see
  "Deployment" below).

**Do not take** (dinary-specific): QR/zbar scanning, the catalog /
rules / receipts / Sheets domain, the analytics stack, the Pinia store
layer, the Cloudflare tunnel alternative, **Litestream and the whole
backup apparatus** (echo-words has no database at all, and its one
durable file — the Anki collection — is already replicated off-box by
the AnkiWeb sync), and its `.deploy/llms.toml` (llmbroker ≥ 1.5.2 is
zero-config: the pool is a curated preset, there is no model-list file
for the operator to write).

**Genuinely new here, with no dinary precedent: streaming.** dinary has
no `EventSource` and no `text/event-stream` anywhere — its requests are
plain fetch. echo-words's SSE pipeline (M3) and its client are original
work; do not expect a pattern to copy.

## Deployment

echo-words is deployed **onto the tenancy's second free-tier instance**
— the one that holds dinary's Litestream replica and otherwise sits
idle — rather than onto dinary's own VM. The reasoning and the measured
comparison are in `spec/decision-deployment.md`.

One deployment target — the difference between it and a dev laptop is
**pure configuration**, never a code path:

- **Home: Oracle Cloud Free Tier `VM.Standard.E2.1.Micro`** — **1 GB
  RAM**, 1/8 OCPU, x86_64. (The Arm `A1.Flex` shape — 2 OCPU / 12 GB
  for Always Free tenancies — is frequently unobtainable per region and
  is not assumed; if available it removes the memory constraints.) A
  **swap file (1–2 GB) is a hard setup requirement**: the web backend +
  Anki pylib + a Piper inference peak coexist in 1 GB only with swap
  behind them. Kokoro is not configured anywhere — it does not fit this
  host, and with the laptop deployment profile dropped it left the
  design entirely (`spec/decision-tts.md`).
- **Tailscale is the front door**: the instance is already in the
  tailnet, and `tailscale serve --bg 8080` maps its tailnet-HTTPS root
  onto the backend's localhost port. The backend binds `127.0.0.1` and
  never sees TLS or auth; tailnet membership is the access control.
- **The laptop is a dev environment**, running the same configuration
  (Piper and edge-tts work anywhere); it is not a supported deployment
  profile.

Model downloads (M6) are driven by the config: only voices referenced by
`languages.toml` are fetched. Full engine rationale and the comparison
table: `spec/decision-tts.md`.

### Rules the host imposes

Why VM2 rather than dinary's own VM, why `invoke` tasks over ssh rather
than Ansible, and why llmbroker keeps its state in a directory of its
own: `spec/decision-deployment.md`, with the measurements behind each.
What follows is what M6 and M8 must actually do.

- **Port**: the backend binds `127.0.0.1:8080`; `tailscale serve --bg
  8080` publishes it at the node's tailnet root.
- **Hostname**: the node keeps its `dinary-replica` tailnet name, so the
  app is published at `https://dinary-replica.<tailnet>.ts.net/` and
  dinary's runbook keeps working unchanged. The odd-looking URL is seen
  once, at install, since the PWA lives on the home screen afterwards.
- **Host preparation is needed here.** VM2 never received dinary's
  hardening pass (`rpcbind` is still running there, which VM1's setup
  disables), so echo-words's `setup-app` runs **with** `--with-host-prep`
  on this box: packages, sshd hardening, fail2ban, swap, and the
  `rpcbind`/iptables step, all ported from dinary. Growing swap to 2 GB
  is cheap insurance with 41 GB free, and capping the journal
  (`SystemMaxUse=200M`) is worth doing on both VMs.
- **Bounded memory anyway.** The unit still sets `MemoryHigh=400M` /
  `MemoryMax=500M`: not to protect a neighbour — there is none — but so
  a runaway is killed as itself instead of taking the box down and
  stranding dinary's replica target. The budget: ~70 MB uvicorn + the
  Anki pylib collection + a Piper inference peak. **The pylib term is
  now measured** — 103 MB peak on this box with the real collection
  (M5), which leaves the limits as they stand and the room for Piper
  intact.
- **Outbound HTTPS to `*.ankiweb.net`** must stay open: sync starts at
  `sync.ankiweb.net` and is redirected to a numbered shard whose name
  varies, so an egress rule pinned to one host would break syncing at
  a random moment. The Anki manual documents the wildcard.
- **The frontend is built on the server**, from the commit the deploy
  just checked out, so `_static/` and the backend can never come from
  two different revisions and no operator's working tree reaches the
  VM. VM1 runs the same Rollup build for dinary's heavier PWA (4 prod +
  9 dev dependencies against this app's 1 + 8) on identical hardware,
  next to a live uvicorn; echo-words builds 23 modules into 82 KB.
- **If VM1 ever dies**, the documented recovery is to restore dinary
  onto VM2, where the two would then share a box — an emergency
  arrangement, and the reason the memory limits above stay in the unit.


### Deploy tasks

Deployment is `invoke` tasks in `tasks/`, ported from dinary and reduced
to what this app needs: `setup-app` (one-time, idempotent),
`deploy --ref=…`, `status`, `logs`, `build-static` (local development,
and the step the deploy runs on the server). Ansible and
Chef were considered and rejected — the argument is in
`spec/decision-deployment.md`.

**What the tasks do**, ported with the dinary-specific parts dropped:

- `setup-app` — repo clone, `uv sync --no-dev`, Node 22 from
  nodesource, `data/` at 0700, the systemd unit, and `tailscale serve
  --bg 8080`.
  `--with-host-prep` adds the host-level pass (packages, swap, sshd
  hardening, fail2ban, the `rpcbind`/iptables step) and is **required
  on the target VM**, which never received dinary's hardening — see
  "Rules the host imposes".
- `deploy --ref=…` — resolve the ref to one commit locally, `git
  checkout --detach` it on the server, `uv sync --no-dev`, build
  `_static/` **there** (`uv run --no-dev inv build-static`), sync
  `.deploy/.env`, re-render the unit, restart, then **poll `GET
  /api/health` until it answers (up to 30 s)** so a failed start fails
  the deploy instead of passing on a fixed sleep. The operator's branch
  and working tree are never read, so a dirty tree is deployable; the
  commit must be reachable from the origin the VM fetches.
- Secrets live in a gitignored `.deploy/.env` with a committed
  `.deploy.example/.env` documenting every variable; the deploy syncs
  the real one to the server, where the systemd unit reads it as
  `EnvironmentFile`. API keys (the paid llmbroker alias's provider key,
  AnkiWeb credentials) never enter the repo.
- `invoke` and `python-dotenv` are **runtime** dependencies: the deploy
  drives the server's own `build-static` task over ssh, so `uv sync
  --no-dev` on the VM has to produce a working `inv`.

**The systemd unit** is dinary's, renamed: `After=/Wants=
network-online.target tailscaled.service`, the `ExecStartPre` wait loop
for `tailscale ip -4`, `EnvironmentFile=…/.deploy/.env`,
`ExecStart` calling the venv's `uvicorn` directly (not `uv run`, whose
cache write conflicts with `ProtectHome=read-only`), `Restart=always`,
and the sandbox block — `NoNewPrivileges`, `ProtectSystem=strict`,
`ProtectHome=read-only`, `ReadWritePaths=` the data dir only,
`PrivateTmp`, empty `CapabilityBoundingSet`, and the rest — **plus the
`MemoryHigh` / `MemoryMax` limits from "Rules the host imposes"**. Note
for echo-words: `ReadWritePaths` must cover `ECHOWORDS_DATA_DIR` (the Anki
collection, the word log, TTS voices, cached audio) — one path, if the
data dir stays under the checkout as it does for dinary.

## Configuration (env vars)

| Variable | Meaning | Default |
|---|---|---|
| `ECHOWORDS_HOST` | interface the web app binds; keep loopback — Tailscale serve is the front door | `127.0.0.1` |
| `ECHOWORDS_PORT` | port the web app binds | `8080` |
| `ECHOWORDS_TARGET_LANG` | language of all explanations and translations, app-wide | `ru` |
| `ECHOWORDS_LANGUAGES_CONFIG` | path to the TOML table defining each source language (see "Languages configuration" below): deck, dictionary code, TTS engine + voice, accent, allowed script, prompt hints | `ECHOWORDS_DATA_DIR/languages.toml` |
| `ECHOWORDS_LLMBROKER_HOME` | directory llmbroker keeps its own state in (curated model list, call journal) — passed as `AsyncBroker(home=...)`. Must be writable: llmbroker falls back to in-memory state where it is not, which silently disables the call journal and with it quality learning. There is **no** model-list file for the operator to write or point at — the pool arrives as a curated preset llmbroker refreshes itself | `ECHOWORDS_DATA_DIR/llmbroker` |
| `ECHOWORDS_LLMBROKER_OPERATION` | operation-label **prefix**; the label actually passed is `{prefix}-{lang}` (`vocab-en`, `vocab-sr`). llmbroker learns quality per `(model, operation)`, so a per-language label makes the pool discover on its own which model is good at which source language — the production counterpart of M0's hypothesis 1 | `vocab` |
| `ECHOWORDS_API_MODEL` | the paid-catalog **alias** the cascade's second step and the deeper-analysis request both use, passed to `broker.direct(...)` (`llmbroker list` prints the catalog). A per-language `api_model` in the languages table overrides it, so one language may step up to a stronger model than the rest. Every alias any language uses is collected at startup and declared as `AsyncBroker(direct=[...])`. Empty disables the second step entirely: the cascade is one step long and no metered call can happen. The provider's key is read by llmbroker from the env var its catalog names (`OPENAI_API_KEY`, …) — echo-words never reads, stores or passes it. M0 measured `gpt-5.6-luna` as the right default: contract-clean, near the quality ceiling, and three times faster than `gpt`; llmbroker's curated catalog carries it under the alias `gpt-fast` | `gpt-fast` |
| `ECHOWORDS_API_DAILY_CAP` | max paid calls per day, counting both cascade step-ups and deeper-analysis requests — one wallet, one cap. Once spent, a pool miss becomes a failure and the deeper-analysis control reports the cap rather than answering from the pool (M2). `0` = unlimited | `100` |
| `ECHOWORDS_ANKIWEB_USER` | AnkiWeb account (email) for sync; required when `ECHOWORDS_ANKI_SYNC` is on | required if sync on |
| `ECHOWORDS_ANKIWEB_PASSWORD` | AnkiWeb password — used once to obtain the sync key (hkey), which is then stored in `ECHOWORDS_DATA_DIR` and reused | required if sync on |
| `ECHOWORDS_SYNC_ENDPOINT` | custom sync server URL (the self-hosted fallback from the decision doc); empty = AnkiWeb | empty |
| `ECHOWORDS_ANKI_SYNC` | sync the collection to AnkiWeb after additions (see M5) | `true` |
| `ECHOWORDS_ACCENT` | `us` or `uk`, English dictionary-audio and voice choice; per-language override in the languages table | `us` |
| `ECHOWORDS_EDGE_TTS_VOICE` | default last-resort edge-tts voice; per-language `edge_tts_voice` in the table overrides | `en-US-AriaNeural` (us) / `en-GB-SoniaNeural` (uk) |
| `ECHOWORDS_AUDIO_TIMEOUT` | seconds to wait for the speculative pronunciation task after generation ends; on timeout the task is cancelled and the send proceeds with "🔇 no audio" (see M6) | `20` |
| `ECHOWORDS_DATA_DIR` | Anki collection (`anki/`), TTS models, downloaded audio, stored sync key — no database of echo-words' own | `~/.echo-words` |

## Languages configuration

`ECHOWORDS_LANGUAGES_CONFIG` points at a TOML file with one entry per
source language, keyed by language code. It is the single source of truth
for everything that varies by language — deck, audio, validation:

```toml
[languages.en]
name       = "English"
deck       = "English::Vocabulary"
dict_api   = "en"              # dictionaryapi.dev code; omit if unsupported
tts        = "piper"           # piper | edge
tts_voice  = "en_US-lessac-medium"
accent     = "us"              # meaningful for English
script     = "latin"           # latin | cyrillic | latin+cyrillic (input validation)

[languages.de]
name      = "Deutsch"
deck      = "German::Vocabulary"
dict_api  = "de"
tts       = "piper"
tts_voice = "de_DE-thorsten-medium"
script    = "latin"

[languages.sr]
name      = "Српски"
deck      = "Serbian::Vocabulary"
api_model = "gpt-fast"             # paid-catalog alias for this language's step-up;
                               # omit -> ECHOWORDS_API_MODEL
# dict_api omitted — dictionaryapi.dev has no Serbian
tts       = "edge"             # no usable local voice: Piper's lone sr_RS model
                               # ("serbski_institut") is actually Lower Sorbian —
                               # never use it (spec/decision-tts.md)
edge_tts_voice = "sr-RS-SophieNeural"
script    = "latin+cyrillic"
prompt_hints = "for nouns give gender and plural, for verbs give aspect"
```

Semantics:

- **Routing.** A submission carries the language code the user selected
  in the UI; it is matched against this table. An unknown code → a
  short hint, no LLM call. The language is always the explicit
  selection, never guessed from the word.
- **Backend.** There is no per-language backend choice: every language
  runs the same cascade, free pool first. A language may only name
  *which* paid model its step-up uses, with `api_model` (a paid-catalog
  alias); absent → `ECHOWORDS_API_MODEL`. Because llmbroker takes its
  declared models at construction, the set of aliases across all
  languages is collected while loading this file and passed to the single
  `AsyncBroker` — so the broker is built *after* the languages config,
  not at import time.
- **Audio.** `dict_api` (omit = skip the dictionary step), `tts` (which
  engine — `piper` for English and German, `edge` for Serbian),
  `tts_voice`, and an optional `edge_tts_voice` (the edge-tts voice —
  primary for Serbian, fallback elsewhere); `accent` where it applies.
  Engine rationale: `spec/decision-tts.md`. See M6.
- **Validation.** `script` selects the allowed character set for the
  language (M1). Because the selection fixes the language before
  validation, the check is exact, not a guess.
- **Prompt hints.** Optional `prompt_hints` — a per-language line
  substituted into the prompt's `{source_hints}` slot (see "The LLM
  contract"); absent → the slot is empty. Keeping hints in the config
  preserves the functional description's rule that adding a language is
  a config change, not a code change.
- Config loads into a `Language` dataclass (new `languages.py`), looked
  up by code. A missing file is a startup config error.

## Web app and API

One FastAPI application (`api.py`) serves everything:

- `GET /` and the build's hashed assets — the PWA, served from
  `_static/` (`StaticFiles`); M8 adds the manifest and icons.
- `GET /api/languages` — the configured languages (code + display name)
  for the selector.
- `POST /api/words` — body `{word, lang, lookup_only, context}`, where
  `context` is optional: the client sends it when the word came from a
  pasted phrase the user picked it out of (M7's picker), and the word
  pipeline passes it into the prompt's `{context_note}` slot. It is free
  text, capped and sanitized like any LLM input, and it never becomes the
  canonical word. Validates (M1),
  assigns an `entry_id`, enqueues the job (M3), and returns
  `{entry_id}` immediately; a validation failure returns the short hint
  instead. The client renders the pending entry from this response.
- `GET /api/events` — the single SSE stream. Events, each carrying the
  `entry_id` they belong to:
  - `accepted` — a job was enqueued (covers submissions from another
    device); payload: word, language, lookup flag.
  - `update` — the **full sanitized text so far** (not a delta): the
    client just replaces the entry's content, which makes missed events
    harmless. Sent at most ~2/s and only when the visible text changed;
    cut at the card delimiter (see "The LLM contract").
  - `done` — final text, the status line, the audio URL (or none), the
    usable `suggestion` (or none) and which spelling the entry
    currently shows.
  - `reset` — drop the text accumulated for this entry so far: the pool
    ran past its budget and the answer is restarted on the paid model (M2).
  - `detail` — deltas of the deeper analysis, appended below the entry's
    analysis rather than replacing it (M7).
  - `error` — a short apology + a hint to send the word again.
  A comment line is sent every 15 s as a keep-alive. The stream carries
  all entries (no per-entry streams): the client opens one
  `EventSource`, and its automatic reconnect plus a `GET
  /api/words/recent` refetch on every (re)connect makes recovery
  lossless.
- `GET /api/words/recent?limit=20` — the history: entries from the
  in-memory ring buffer (word, language, sanitized analysis HTML,
  status, audio URL) including in-progress ones with their accumulated
  sanitized text, newest first. Empty after a restart, by design.
- `POST /api/words/{entry_id}/switch` — the correction button (M7):
  re-runs the pipeline for the other spelling into the same entry.
- `POST /api/words/{entry_id}/rebuild` — rebuild this entry's card with the
  paid model (M7), using the entry's context when it has one. Re-runs the
  normal card-producing prompt, replaces the note the entry created, and
  keeps the audio — it belongs to the word, which does not change. Refused
  with a reason when no paid alias is configured or the daily cap is spent.
- `POST /api/words/{entry_id}/detail` — the deeper-analysis control (M7):
  asks the paid model for the extended brief on the same word and streams it
  into the same entry as a second block, leaving the analysis, the note and
  the audio untouched. Idempotent — a second call returns the text already
  kept on the entry without paying again. Refused with a reason when no paid
  alias is configured or the daily cap is spent.
- `POST /api/languages/{code}/undo` — per-language undo (M7).
- `GET /api/stats`, `GET /api/status` — the stats and status views (M7).
- `GET /api/audio/{name}` — serves a stored pronunciation mp3 from
  `ECHOWORDS_DATA_DIR/audio/` (filenames are server-generated slugs —
  never client-supplied paths; reject anything but a bare known
  filename).
- `GET /api/health` — a **machine-readable liveness probe**, distinct
  from the user-facing `/api/status`: it answers as soon as the app is
  serving, touches no LLM and no network, and is what the deploy task
  polls before declaring a release good. Ships in M1 with the skeleton,
  because the deploy depends on it.

Frontend rules: Vue 3 in `webapp/`, built to `_static/`, state in
composables rather than a store library (see "Reuse from dinary"). The
app keeps the selected language in
`localStorage`, renders entries from `/api/words/recent` + live events,
plays audio via an `<audio>` element (autoplay attempted, one-tap replay
always available), and keeps a resend queue of words that failed to POST
(M8). Server-sent analysis HTML is already sanitized (see "The LLM
contract") and is the only thing rendered with `v-html`; everything else
is interpolated as text.

## Word pipeline (orchestration)

`pipeline.py` owns one coroutine shared by every entry point — the
submit endpoint (M3), the correction switch and the card rebuild (both M7):

```python
async def process_word(lang: Language, word: str, lookup_only: bool,
                       reuse_entry: str | None = None) -> None
```

1. The submit endpoint validates, assigns an `entry_id`, registers the
   job in the in-memory registry and enqueues it, then returns — the
   entry appears as pending at once, and submissions keep their order.
   When `reuse_entry` is given (correction switch, rebuild), the existing
   entry is reset to pending instead of a new one being created.
2. The single queue worker takes jobs in submission order (a FIFO
   `asyncio.Queue`, one worker — no parallel LLM runs, even across
   languages) and runs the steps below.
3. Start the speculative audio task for the raw input — parallel with
   the LLM call (M6).
4. Run `stream_completion(prompt, lang)` — the cascade: the pool, then
   the paid model where the pool missed the budget (M2). Accumulate the
   raw text server-side, publish sanitized `update` events cut at the
   delimiter (M3). The accumulated text is what `/api/words/recent`
   serves for an in-progress entry. A step-up that happens mid-stream
   publishes a `reset` event first, so the page drops the abandoned
   partial text instead of splicing two answers together.
5. Parse the card payload out of the raw text (M4). On parse failure the
   analysis text still stands; the status line will report that the card
   failed.
6. `await asyncio.wait_for(audio_task, ECHOWORDS_AUDIO_TIMEOUT)`; store
   the mp3 and note its URL; on timeout or `None`, note "🔇 no audio"
   for the status line (M6).
7. Add the note unless lookup-only, duplicate, or parse failure (M5);
   compose the status line.
8. If the payload carried a usable `suggestion`, include it in the
   `done` event so the UI renders the correction button (M7). The `done`
   event also names which model answered and whether a deeper analysis is
   available for this entry (M7).
9. Update the history entry in place (final sanitized analysis, status,
   audio URL), bump the session counters, and update the language's
   undo state (M7); publish `done`.

The function grows one step per milestone, leaving earlier steps
untouched — the milestones below reference these step numbers.

## The LLM contract (core of the system)

`prompt.py` builds one prompt per request from a template with two
language slots — the source language (the user's selection, M1) and the
target language (`ECHOWORDS_TARGET_LANG`). The `===CARD===` JSON contract
below is identical across languages; only the two slots and an optional
per-language morphology hint change:

```text
You are a vocabulary tutor. The word below is in {source_lang}. Analyse
this word or short phrase: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}.
This is absolute. Every part of the answer — the translations, the labels,
the register marks, the usage notes, the origin, the explanations of the
examples — is written in {target_lang}, and in no other language. These
instructions are in English; that says nothing about the answer language.
Do not answer in English unless {target_lang} IS English. Do not answer in
{source_lang} unless {target_lang} IS {source_lang}. Two things, and only
these two, stay in {source_lang}: the headword itself and the example
sentences (each of which is followed by its {target_lang} translation).

{context_note}Be compact. No preamble, no closing remarks. {source_hints}
The order of the sections is fixed:

1. First line: the word being analysed, in bold.
2. Translations, most frequent in everyday speech first; each with its
   part of speech and a register mark (colloquial, formal, slang, vulgar
   and so on) where it matters.
3. Usage: typical collocations and prepositions, what it is confused
   with; countability and irregular forms where they matter.
4. Origin: if the word was borrowed, 1-3 sentences on which language it
   came from and how it travelled; for a native word, one line.
5. Examples: 2-4 short everyday sentences, each followed by its
   translation.

Give no phonetic transcription: pronunciation is delivered as audio.

Analyse EXACTLY the word given and do NOT substitute another. If it looks
like a typo, do not silently fix it: add one short line beginning with ✏️
and naming the likely intended spelling, and put that spelling in the
suggestion field of the card JSON. If there is no typo, suggestion is an
empty string.
If it is an idiom or a phrasal verb, explain both the literal and the
figurative sense and when it is used.
ALL EMPHASIS IS HTML. Use exactly two tags and no others: <b> around the
headword, <i> around the {source_lang} example sentences and any
{source_lang} form quoted inside the text. Emphasis punctuation of any
kind is forbidden — no markdown, no headings, no bullet markers, no
tables, no code fences.
The whole analysis: at most 3500 characters.

After the analysis output the line ===CARD=== exactly, and immediately
after it one line of JSON, with no commentary and no HTML tags inside the
values:
{"word": "...", "suggestion": "...",
 "meanings": [{"label": "...", "pos": "...", "translations": ["...", "..."],
 "examples": [{"text": "...", "translation": "..."}]}]}
word — the input word exactly as given (never corrected); suggestion — the
likely intended spelling of a typo, or an empty string.
meanings normally holds one element with an empty label. Split it into
several (at most three) only when the senses are genuinely unrelated (like
bank "financial institution" and bank "river edge"); then label is a
1-3 word tag in {target_lang} telling the senses apart. pos is that
sense's part of speech as one short abbreviation in {target_lang}.
translations — the 2-4 main {target_lang} translations of that sense;
examples — the 1-2 shortest examples of that very sense: text is a
sentence in {source_lang}, translation is its rendering in {target_lang}.
In at least one example per sense, use the headword in exactly the form it
was given, unless that makes the sentence unnatural.

Before you answer, check two things once more. Is every word of it in
{target_lang}, except the headword and the {source_lang} example
sentences? And is every emphasis an HTML tag, with no punctuation used
for emphasis anywhere?
```

`{context_note}` is empty for a plain word. When the user submitted a phrase
and tapped a word in it, it carries the phrase and the instruction to answer
for the sense used there — the point of context is a meaning no dictionary
lists, so the slot must also permit "this use is rare/non-standard" as an
answer instead of forcing the word into a dictionary sense:

```text
The word was met in this context: "{context}"
Analyse the sense in which it is used there. If that sense is rare,
domain-specific or not recorded in dictionaries at all, say so plainly and
explain that sense — do not substitute the nearest dictionary meaning.
```

`{source_lang}` / `{target_lang}` are the language display names, and
`{source_hints}` is filled from the language's optional `prompt_hints`
field in `languages.toml` (e.g. for Serbian: "for nouns give gender and
plural, for verbs give aspect"); when the field is absent the slot is
empty — so a new language, hints included, needs no code change.

**The prompt is written in English, and the answer language is a slot.**
One decision with two reasons: English is what models follow instructions in
most reliably, and the target language must be free to be anything, so it
cannot be baked into the prose. `prompt_hints` is an instruction to the model
and is written in English for the same reason.

Nothing about the prompt's own language may reach the answer, and an English
prompt is exactly what makes a model likeliest to mirror it, so the
target-language demand is stated three times: at the top, in the body naming
the two things that stay in the source language, and at the end as a check
the model runs before answering. Measurements behind the wording are in
`spec/decision-llm-backend.md`.

Parsing rules (`prompt.py` / `card.py`):

- Everything before `===CARD===` is the visible analysis. During
  streaming, cut the displayed text at the delimiter as soon as any
  prefix of it appears at the end of the buffer (never flash `===CA` to
  the user).
- After the run, parse the JSON after the delimiter into a single
  `Note` (`word`, `meanings: list[Meaning]` where each meaning
  has `label` possibly empty, `pos` possibly empty (the part-of-speech
  fallback for the recall front, M5), `translations: list[str]` non-empty,
  `examples: list[Example]`, where `Example` has `text` — the sentence
  in the source language — and `translation` — its target-language
  rendering); reject an empty meanings list or more
  than three meanings. A missing `pos` is tolerated and defaults to `""`.
  Also read the optional `suggestion` string (a
  typo hint — see "Autocorrection: advisory only" in the functional
  description); it is transient UI state, not part of the stored note, so
  it is returned alongside the `Note`, not on it. A missing or empty
  `suggestion` means "no correction offered". On any parse/validation
  failure: the analysis still stands, no note is created, the status
  line says the card failed — never crash the pipeline.
- The **canonical word is always the raw input**, never the LLM's output:
  autocorrection is advisory, so the payload's `word` merely echoes the
  input and is not trusted for identity. Together with the source language
  the raw input is the key for the duplicate check (case-insensitive,
  scoped to the language's deck), the history entry,
  undo state, the Anki `Word` field, and the speculative audio fetch
  (M6) — which is therefore always the right audio, with no re-fetch in
  the normal flow. `suggestion`, when non-empty and different from the
  input (case-insensitive), is the only thing that triggers UI: the
  word pipeline includes it in the `done` event so the correction button
  appears (step 8; the button logic is M7). The
  corrected word runs downstream only if the user taps that button, which
  re-processes the word exactly as a fresh send for the suggested
  spelling.
- `suggestion` is the **one piece of LLM output that can still become a
  canonical word**, so it must clear the same gate as typed input before
  any button is offered: the M1 per-language validation (script, allowed
  punctuation, length) applied with the word's own source language. A
  suggestion that fails it is dropped exactly like an empty one — the
  analysis and the card for the typed word are unaffected, there is just
  no button. This keeps a hallucinated "correction" out of the deck, and
  out of the `find_notes` query and the media filename it would reach
  through the re-run (M5).

### The extended prompt (deeper analysis)

The deeper-analysis control (M7) uses a second template from the same module,
and its differences from the one above are all consequences of one fact: **it
produces no card.** So it has no `===CARD===` contract, no meaning cap, no
3500-character ceiling, and nothing it returns can reach the deck or fail a
parse. It is an independent, fuller analysis of the same word — not a diff
against the first answer, which would mean feeding the first answer back and
making the call stateful for no gain.

```text
You are a lexicographer. The word below is in {source_lang}. Analyse this
word or short phrase in depth: {word}

WRITE YOUR ENTIRE ANSWER IN {target_lang}, and in no other language. These
instructions are in English; that says nothing about the answer language.
Only the headword and the example sentences stay in {source_lang}, and
every example is followed by its {target_lang} translation.

{context_note}The reader has already seen the short entry, so do not skimp
on detail — but stay on the point in every section.

1. First line: the word being analysed, in bold.
2. EVERY sense, not only the frequent ones: figurative, domain-specific,
   archaic, regional and slang alike. For each, the part of speech, the
   register mark, and the field it belongs to. If a sense lives only in a
   particular domain (law, medicine, sport, jargon), name that domain.
3. Origin, in depth: the source language, the original form and meaning,
   the route the word travelled, when it entered the language, related
   words within the language and cognates elsewhere. For a native word,
   the root and how it developed. Where the etymology is disputed, give
   the competing accounts.
4. Usage: set phrases, government, register, what it is confused with,
   false friends, the mistakes learners typically make.
5. Shades and near-synonyms: how it differs from them and which is apt
   where.
6. Examples: one or two per sense from section 2, each followed by its
   translation.

For emphasis use ONLY the HTML tags <b> and <i>: the headword in bold, the
{source_lang} examples in italics. No markdown, no other tags. Give no
phonetic transcription. No JSON and no delimiters of any kind — this is
reading matter only.
```

The same sanitizer applies, for the same reason. The one new failure mode is
that a model may emit a `===CARD===` block out of habit; the extended text is
cut at the delimiter exactly as the analysis is, so a stray payload is
discarded rather than shown.

HTML safety (`sanitizer.py`): the LLM is only *asked* to emit
`<b>`/`<i>` — the code must enforce it, because the client assigns the
analysis as HTML. The sanitizer runs **server-side** over the
accumulated text before anything is published (SSE events, the history
endpoint) — the client never sanitizes and never receives unsanitized
LLM output: escape `&`, `<`, `>` everywhere except whitelisted `<b>`,
`</b>`, `<i>`, `</i>` tags; auto-close tags left open at the current
cut point (streaming can split a tag pair across updates).

## Module layout

```
src/echo_words/
  __about__.py      # version (exists)
  __init__.py       # exists
  config.py         # Settings
  languages.py      # Language dataclass + languages.toml loader; lookup by code
  main.py           # the existing `echo-words` click command, reduced to a server
                    # launcher: it keeps --version (the scaffold's test covers it)
                    # and runs uvicorn on ECHOWORDS_HOST:ECHOWORDS_PORT. The app
                    # object itself is built in api.py, so the deploy's ExecStart
                    # can call uvicorn directly without importing click
  api.py            # FastAPI routes (submit, events SSE, recent, switch, undo,
                    # stats, status, audio) + static mounting
  pipeline.py       # process_word + the single FIFO queue worker + in-memory job registry
  events.py         # in-process pub/sub bridging pipeline progress -> SSE subscribers
  sanitizer.py      # whitelist <b>/<i>, escape the rest, auto-close at the cut
  backend.py        # stream_completion dispatcher: the pool first, the paid step where
                    # the pool missed the budget; enforce ECHOWORDS_API_DAILY_CAP —
                    # a spent cap is a failure, never a fallback to the pool
  broker.py         # the one AsyncBroker: built after languages.py from home= + direct=[aliases]
  llm_backend.py    # llmbroker pool backend: broker.stream(...) -> text deltas
  api_backend.py    # paid api backend: (await broker.direct(alias)).stream(...) -> text deltas
  prompt.py         # prompt template (source/target lang slots) + card-payload extraction
  card.py           # note dataclass (word, 1-3 meanings) + optional suggestion,
                    # validation of the LLM payload
  anki.py           # headless collection wrapper (pylib): open/bootstrap, add/find/delete
                    # notes, media, debounced AnkiWeb sync
  audio.py          # per-language chain: dictionary + Piper + edge-tts -> mp3
  history.py        # in-memory ring buffer of recent entries + the session counters
                    # (duplicates, lookups); the source for /api/words/recent

webapp/             # Vue 3 + Vite PWA sources (see "Reuse from dinary")
  package.json      # vue; dev: vite, @vitejs/plugin-vue, vite-plugin-pwa, vitest
  vite.config.js    # build.outDir "../_static", /api dev proxy, workbox strategy
  index.html
  src/
    main.js  App.vue
    assets/base.css     # design tokens, ported from dinary
    api/_request.js     # fetch wrapper (ported)
    composables/        # state lives here as module-level refs, no store library:
                        # useEntries (the entry list + history), useQueue (resend
                        # queue), useLanguage (selection, persisted); plus ported
                        # useOnline, swHealth, useKeyboardVisible, flushQueue;
                        # useEventStream (new — the SSE client, M3)
    views/              # AddView (input + history), StatsView, StatusView
    components/

_static/            # build output, gitignored; served by the backend
tasks/              # invoke deploy tasks, ported from dinary (see "Deployment")
```

`[project.scripts]` already carries `echo-words = "echo_words.main:echo_words"` —
keep it; do not add a second entry point.

## Milestones

Each milestone = one or more commits, tests included, CI green. **M0 is the
exception**: a research spike whose harness lives in `experiments/`, calls
real models and never enters CI.

### M0 — LLM backend spike (done; precedes M1–M8)

A research spike, run before any product code, that measured both steps of the
cascade per source language and set the defaults the rest of the plan builds
on. Its harness is `experiments/backend_bench.py` — outside the package and
outside CI, it calls real models and its paid phase spends real money.

Everything it settled, and the numbers behind it, is
**`spec/decision-llm-backend.md`**, which is an input to M2. Nothing else in
this plan restates it.

### M1 — config + web app skeleton

The Python side of the dependency set is already in `pyproject.toml` and
`uv.lock` — `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`
(the last one is also what the in-process test client needs); the
`webapp/` scaffold brings its own `package.json`. Later milestones add
`llmbroker` (M2), `anki` (M5) and the TTS stack (M6).

`config.py`, `languages.py`, `main.py`, `api.py`, plus the `webapp/`
scaffold: the application starts, answers `GET /api/health`, serves
`GET /` (the built page: a language selector fed by `GET
/api/languages`, an input box with the lookup-only control, and an empty
answer area) and accepts `POST /api/words`.
The `webapp/` scaffold is created here — `package.json`,
`vite.config.js` (workbox strategy, `outDir: "../_static"`, `/api` dev
proxy), `assets/base.css` ported from dinary, `api/_request.js`, and the
`AddView` shell — so every later milestone has a page to render into;
`inv build-static` and `inv dev` work from this milestone on.
`languages.py` loads `ECHOWORDS_LANGUAGES_CONFIG` into `Language`
objects indexed by code; a submission's `lang` selects the language, an
unknown code gets a short hint and no processing. Input validation is
per the resolved language's `script` (Latin incl. accented — café,
naïve, Straße — for en/de; Latin or Cyrillic for sr; plus spaces,
hyphens, apostrophes; max ~50 chars; otherwise a short hint). A submission carrying more than one word is not
validated as a word at all: the app resolves it to a word plus a context
before submitting (M1 accepts both shapes; the picker itself is M7). The
chosen word is validated exactly as a typed one; the context is free text,
capped in length and sanitized like any LLM input, and it never becomes the
canonical word. A leading
`?` (with optional space) marks the request lookup-only and is stripped
before validation — same for the explicit `lookup_only` flag. For this
milestone the accepted submission gets a stub response naming the
resolved language (the queue and events arrive in M3). The help/about
note on the page is written once, here, and must already describe the
lookup-only control, the `?` shortcut, AND the ✏️ correction button
offered for a suspected typo (the button itself ships in M7), as the
functional description requires. Tests (in-process test client): the
languages loader (code lookup, missing file), per-language validation
incl. the `?` prefix and Cyrillic-vs-Latin per language, unknown
language code → hint, the stub flow, `/api/health` answering, and static
page serving. Vitest + Vue Test Utils tests cover the HTTP helper, persisted
language selection and the `AddView` submission/help behavior in happy-dom.

### M2 — LLM backend runner (the pool → paid cascade)

One seam, one cascade, both steps shipped here. The pipeline calls
`stream_completion(prompt, lang, trace_id=…, on_reset=…)` (in a small
`backend.py` dispatcher), which hands back one object — async-iterable over the
text deltas, carrying `llm_name`, `record_quality()` and `aclose()`, the same
shape llmbroker's own handle has — and which always starts at the pool and steps up to the
paid model on **one** trigger, latency and not a per-language choice: **the pool
did not deliver a complete answer within its attempt budget.** llmbroker's
`wait` covers the whole answer in provider time, so that one budget is the
whole rule for the pool attempt — it does not matter whether the pool never
started or started at once and kept going, and echo-words keeps no clock of
its own.

Where the budget ran out decides only what the user sees. Before any text was
published the step-up is invisible beyond a status line; once text is on the
page the dispatcher tells the pipeline to publish `reset` and starts the paid
step from the beginning of the same prompt, so two answers are never spliced.

**Time to the first token is never measured, here or anywhere.** The functional
description states why: it is the number a slow model looks best on, and the
user waits for the whole answer.

Anything that is *not* latency — a dead key, an empty or disabled pool, a
malformed request — is a `BackendError`, not a step-up: the cascade buys time,
it does not paper over faults. With no paid alias configured or the daily cap
spent, there is no second step at all, and a pool timeout is also surfaced as
a `BackendError` carrying that refusal reason.

- **`llmbroker` backend** (`llm_backend.py`): one process-wide `AsyncBroker`
  lives in `broker.py`, built in the FastAPI lifespan after the languages
  config with `home=ECHOWORDS_LLMBROKER_HOME` and `direct=[…aliases…]` (see
  "Languages configuration") and `aclose()`d on shutdown. Per request
  `handle = broker.stream(prompt, operation=f"{prefix}-{lang.code}",
  trace_id=…, wait=…)`, iterated inside `contextlib.aclosing(handle)` so the
  model's slot is handed back even when the pipeline abandons the stream —
  deltas go straight into the pipeline. `wait` carries the functional
  description's complete-answer budget, at its low end: it bounds queueing and
  the whole answer in provider time, so a budget exhausted past the first delta
  raises `LLMTimeoutError` with the deltas so far already delivered — which the
  low end is chosen to avoid (`spec/decision-llm-backend.md`). It is an HTTPS text→text
  call the operator already trusts — no subprocess, nothing to sandbox. Map
  `NoLLMAvailableError(reason="timeout")` (whole pool rate-limited),
  `LLMTimeoutError` and
  `StreamInterruptedError` (the stream died after deltas — no failover
  possible past the first one) onto one `BackendError` so the error path is
  uniform. Import `llmbroker` lazily so a missing/broken install degrades to a
  clear config error, not a startup crash — a sanctioned exception to the
  top-level-imports rule; mark it with a comment. The seam hands the handle (or just
  its `llm_name` and a rating callback) back to the pipeline alongside the
  deltas, because both of the following need it:
  - **Quality feedback ships in v0.1:** after the card is parsed (M4),
    `await handle.record_quality(1.0 if parsed else 0.0)` — the handle knows
    its own model, operation and call id, so there is no journal read and no
    id to persist. It is rateable only once the answer has ended, which is
    where this runs; rating an abandoned stream is skipped rather than
    retried. A clean card JSON is a genuine automatic quality signal and costs
    nothing, and the per-language `operation` label means the pool learns
    which model handles which source language.
  - **`handle.llm_name`** is recorded in memory with the call's outcome and
    time, for `/api/status` (M7).

  (First task of the milestone: the one-line sanity check from "Upstream
  dependency" that the installed llmbroker's `StreamHandle` carries
  `record_quality` and `llm_name`.)
- **`api` backend** (`api_backend.py`): the cascade's second step, and the
  model the deeper-analysis request (M7) always uses. Delegates to
  **llmbroker's direct client** — a single named frontier model, no pool, no
  failover: `client = await broker.direct(alias)` on the same `AsyncBroker`
  instance the pool backend holds, where `alias` is the language's `api_model`
  or `ECHOWORDS_API_MODEL`, then `async for delta in client.stream(prompt)` —
  here a plain async iterator, not a handle. The client borrows the broker's
  one shared httpx client, so fetching it per request is cheap and it must
  **not** be closed by echo-words. The alias must already be in that broker's
  `direct=[…]` — collected while loading the languages config — or `direct()`
  itself raises `UnknownModelError` / `PoolModelError` / `MissingKeyError`.
  The key never passes through echo-words: the catalog entry names an env var
  and llmbroker reads it at call time. Map those and the call's own errors
  (`AuthError`, `RateLimitError`, `LLMTimeoutError`, `ProviderError`,
  `InvalidProviderResponseError`) onto the same `BackendError`, so the error
  path stays uniform. Its timeout is a fresh complete-answer budget of the same
  size as the pool's; an emergency step-up can therefore consume two windows
  end to end. The failed pool does not shorten the paid model's allowance. Note
  the direct client is **not journaled**, so it has
  no `llm_name`, no quality feedback and needs none — a declared model is
  never routed, there is nothing for a score to inform, and `/api/status`
  names the configured alias itself. **Daily spend cap:** the `backend.py`
  dispatcher counts every paid call — step-ups and deeper-analysis requests
  alike, one counter for the whole app, since it is one wallet. Once
  `ECHOWORDS_API_DAILY_CAP` is reached the second step is simply gone for the
  rest of the day: a pool miss becomes a `BackendError` the user sees, and the
  deeper-analysis request is refused with the reason. That is the honest
  behavior — falling back to the pool would answer a question the user asked
  the paid model. The cap state is surfaced in `/api/status` (M7). The counter
  lives in memory and resets on restart — acceptable for a personal tool.

Tests: for the **llmbroker backend** a fake `AsyncBroker` whose `stream()`
returns a fake handle (monkeypatched — no real pool) asserting the happy path
yields streamed deltas as multiple chunks, that the per-language `operation`
label (`vocab-en`, `vocab-sr`), `trace_id` and `wait` are passed through, that
the handle is closed even when the consumer abandons the stream mid-way, that
`NoLLMAvailableError` surfaces as a budget miss only for `reason="timeout"`
and as a non-step-up fault for every other documented reason, that
`LLMTimeoutError` and `StreamInterruptedError` surface as `BackendError`, that
a parsed card calls `handle.record_quality`
with a positive score and a parse failure with the opposite, that
`handle.llm_name` is recorded for `/api/status`. For the **cascade** itself:
that a pool stream which yields nothing within the budget steps up invisibly,
that one which starts and then outlives the budget steps up with a `reset`, that
a non-latency failure does *not* step up, and that a completed pool answer never
touches the paid client. For
the **`api` backend**: a fake
direct client (monkeypatched — no real provider) asserting streamed deltas
arrive as multiple chunks, that the language's `api_model` overrides
`ECHOWORDS_API_MODEL` and that every configured alias is present in the
broker's `direct=[…]`, that the client is never closed by the backend, that
resolution errors (`UnknownModelError`, `PoolModelError`, `MissingKeyError`)
and call errors (auth/rate-limit/timeout/provider) all surface as
`BackendError`, and that once `ECHOWORDS_API_DAILY_CAP` is hit the second step
disappears — a pool miss raises instead of paying, and a deeper-analysis
request is refused — with the counter covering both kinds of paid call.

### M3 — queue + streaming over SSE

`pipeline.py`, `events.py`, `sanitizer.py`, and the SSE endpoint:

- **The queue.** Words are processed strictly one at a time **and in the
  order submitted**: a single FIFO `asyncio.Queue` drained by one worker
  task, spanning all languages (no parallel LLM runs). The submit
  endpoint registers the job and enqueues it before returning, so the
  response (and the `accepted` event for other devices) shows the
  pending entry immediately while the worker catches up.
- **Streaming.** The worker accumulates raw deltas, cuts at the
  delimiter (never flash `===CA…` — see the LLM contract), sanitizes,
  and publishes `update` events carrying the full sanitized text so
  far — at most ~2/s and only when the visible text changed. The final
  `update` carries the complete text; the status line and everything
  after it (M5–M7) are layered onto the `done` event by later pipeline
  steps. The accumulated sanitized text is also what
  `/api/words/recent` returns for an in-progress entry, so an SSE
  reconnect refetch is lossless.
- **Events plumbing.** `events.py` is a small in-process pub/sub: the
  SSE endpoint subscribes (one subscriber per open `EventSource`,
  multiple allowed — phone + desktop), the pipeline publishes. A
  keep-alive comment every 15 s; a slow/gone subscriber is dropped, it
  recovers by reconnect + refetch.
- **Errors.** On `BackendError`: publish an `error` event with a short
  apology and a hint to send the word again; the entry keeps any text that
  already streamed.
- The `reuse_entry` path (correction switch / rebuild, M7) resets the
  existing entry to pending and streams into it instead of creating a
  new one.

The client side of this milestone is `useEventStream` — the one
composable with no dinary precedent: it opens a single `EventSource`,
applies `update` events by **replacing** an entry's content (never
appending, so a missed event is harmless), and on every open or
reconnect refetches `/api/words/recent` to resynchronize. Browser
`EventSource` reconnects on its own; the composable's job is the
refetch and the entry bookkeeping.

Tests: scripted delta sequences through a fake backend → recorded event
stream (update cadence, delimiter cutting, final text, error path);
vitest for `useEventStream` — an update event replaces rather than
appends, and a reconnect triggers the refetch;
sanitizer cases — stray `<`/`&`, disallowed tags escaped, `<b>` split
across two deltas, unclosed `<i>` auto-closed at the cut; two words
submitted together → both appear immediately and the LLM runs execute
one at a time in submission order; `/api/words/recent` returns the
accumulated text of an in-progress entry; the reuse-entry path updates
the existing entry and never creates a second one; two subscribers both
receive events.

### M4 — card extraction

`card.py` + prompt module: parse the payload per the LLM contract,
including the optional `suggestion` string returned alongside the `Note`
(absent, empty, and present-and-different cases). Tests: valid
single-meaning payload, valid multi-meaning payload (2-3 meanings with
labels), payload with trailing garbage, missing delimiter, malformed
JSON, empty translations, empty meanings list, four meanings (rejected),
missing `pos` (tolerated, defaults to `""`), payload with a `suggestion`
and payload without one (both parse; the suggestion never affects note
validity), and a `suggestion` that fails the language's input validation
(dropped exactly like an empty one — the note still parses, no button).

### M5 — Anki integration (headless pylib)

**The sync spike that gates this milestone is done** (harness:
`experiments/anki_headless_spike.py`, outside the package and outside
CI, like M0's — it deliberately hits real AnkiWeb, which stays out of
the test suite). Run on VM2 itself against the real account with
`anki==26.8.1`: headless `sync_login` works, a fresh collection
bootstraps by downloading the existing AnkiWeb collection, and a note
with audio added server-side arrives on AnkiDroid — confirmed by ear,
and independently by a second fresh collection that pulled it back from
AnkiWeb. The harness also proves the fallback: the same round trip
through Anki's own self-hosted sync server. Re-run it after any `anki`
version bump; `--cleanup` removes what it adds.

**Four rules the spike produced — the implementation must follow them:**

- **Follow the endpoint AnkiWeb hands back.** Both `sync_status` and
  `sync_collection` may return a `new_endpoint` (a shard such as
  `sync10.ankiweb.net`); whether they do varies per session. Rebuild
  `SyncAuth` with it and use that for everything after, exactly as
  `qt/aqt/sync.py` does with the profile's sync URL. Skipping this
  makes the full download fail with an opaque
  `HttpError 400 "missing original size"` — the shard's response lacks
  a header the client requires.
- **A full transfer needs the collection closed and reopened around
  it** — `close_for_full_sync()` before, `reopen(after_full_sync=True)`
  after. The Rust backend reopens the collection itself; without this
  the Python object keeps a handle to a database that is gone.
- **Never touch the schema after the first sync.** Removing or
  restructuring a note type is a schema change, after which AnkiWeb
  demands a one-way full sync — which the safety rule below forbids,
  so the change would sit unsynced forever. Creating the note type and
  the language decks does *not* trigger this and syncs normally. If a
  pre-existing `EchoWords` note type is misconfigured, fail with the
  status-line error as specified below; never "fix" it by deleting it.
- **Treat a `FULL_SYNC` answer as an error, not as a no-op.** It means
  the changes were not pushed. Surface it (M7's `/api/status`) instead
  of letting a silent branch swallow it.

**Measured on VM2, 2026-08-17** (the collection: 4362 notes, 5141
cards, 33.4 MB, plus 1353 media files at 82 MB):

- **Peak RSS 103 MB** with the collection open and a media sync
  running; 91 MB with it open and idle; 71 MB on an empty collection.
  With uvicorn's ~70 MB that fits the unit's `MemoryHigh=400M` /
  `MemoryMax=500M` and leaves room for M6's Piper — the limits stay as
  "Rules the host imposes" sets them, and the escape hatches (trim the
  collection to echo-words's own decks, or move to the Arm shape) stay
  unused.
- **A steady-state sync is free**: 0.02 s for the collection and 0.2 s
  for media when nothing changed, so the 5-minute debounce is
  generous rather than tight. Only the first run is slow — 0.9 s for
  the collection download and 43 s to fetch the whole media library.
- **Disk: ~115 MB** for collection plus media, against 40 GB free.

`anki.py` wraps a headless `anki.collection.Collection` at
`ECHOWORDS_DATA_DIR/anki/collection.anki2` (directory created on first
run; the bootstrap full-download above applies when sync is on). pylib
is blocking — run every collection call in `asyncio.to_thread`; the
single queue worker (M3) already serializes writers, and the process is
the collection's only writer by design. On first use: ensure the note
type `EchoWords` exists and, on first use of a language, that language's
deck (from the languages config) exists. When the note type is already
present — the first-run download brings the user's entire AnkiWeb
collection, which may well carry one from an earlier version or a
hand-made one — verify its field names and its two template names
against the expected set (`col.models.by_name`, then its `flds` and
`tmpls`); on mismatch fail with a clear status-line error ("note type
EchoWords is misconfigured — fix or delete it in Anki") rather than feed
notes into a model with unknown fields. No auto-migration in v0.1. Note
type fields: `Word`, `Translations`, `Meanings`, `Audio`; two card
templates:

- **Recognition** — Front: `{{Word}} {{Audio}}`, Back: `{{Meanings}}`.
- **Recall** — Front: `{{Translations}}`, Back: `{{Word}} {{Audio}}` —
  exactly the word and its audio, as the functional description fixes
  the recall back; do NOT append `{{Meanings}}` here.

Minimal CSS. `Translations` and `Meanings` are rendered by the backend
from the parsed payload. `Translations`: one block per meaning — label
in bold (only when the note has more than one meaning), that meaning's
translations, and below them **one gapped example**: the first example
of that meaning containing the canonical word, with every occurrence of
it replaced by `___`, followed by the example's translation. The match
is a plain case-insensitive whole-word search for the canonical word
exactly as the user typed it — no stemming and no per-language
morphology, so the rule behaves identically in every configured language
and a new language needs nothing added. When no example of a meaning
contains the word that way (an inflected form, a German separable
prefix), that meaning falls back to its `pos` value in place of the
example; when `pos` is empty too it shows its translations alone. An
unmasked example must never reach this field — the front would give the
answer away — but a bare translation alone leaves the reviewer guessing
which source word is wanted (посылка → parcel / package / shipment),
which is exactly what the gap resolves. `Meanings`: one block per
meaning — label in bold (same condition), translations on one line,
examples in italics with their target-language translations — numbered
`<ol>`-style when there is more than one block. Every payload value is
HTML-escaped before being wrapped in tags: Anki fields are HTML, and the
prompt only *asks* the LLM to keep tags out of JSON values — a stray `<`
or `&` must not break the card.

One word = one note, so the first field (`Word`) is naturally unique.
Duplicate check before adding: `col.find_notes()` with query
`deck:"{deck}" note:EchoWords "Word:{word}"` — `{deck}` is the language's
deck and `{word}` the **canonical word, i.e. the raw user input** — never
the payload's `word` echo, which merely repeats the input and is not
trusted for identity (see the LLM contract); case-insensitive
match is Anki's default. Scoping by deck is what lets the same spelling
exist in two languages without a false duplicate. If a note exists,
nothing is added and the send reports duplicate.

`add_note(note, deck, audio_path)` (deck from the word's language) returns
`added(note_id) | duplicate`;
audio is copied into the collection's media with `col.media.add_file`
under the name `echo-words-{slug}-{hash}.mp3` (where `slug` is the
lowercased canonical word with non-alphanumeric runs collapsed to `-`
and `hash` is the first 8 hex chars of the canonical word's SHA-1 —
distinct phrases that slugify identically, like "go over" vs "go-over",
must not overwrite each other's media; `add_file` may return an
adjusted name — use the returned name) and referenced as `[sound:...]`
in the `Audio` field. Skipped entirely for lookup-only requests —
status line "👁 lookup only". Wire into the pipeline (step 7): the
status line joins the `done` event. Because the collection is
in-process, `add_note` cannot fail with "Anki is not running" — there
is no pending-card queue anywhere in the design. Track the last added
note id AND its media filename (the name `add_file` returned) in memory
for undo and the rebuild (M7), which remove both.

After every successful add the client schedules the **AnkiWeb sync**
(pylib: `sync_collection(auth, sync_media=True)`): on first need,
`sync_login(ECHOWORDS_ANKIWEB_USER, ECHOWORDS_ANKIWEB_PASSWORD,
endpoint=ECHOWORDS_SYNC_ENDPOINT or None)`, then persist the returned
hkey in `ECHOWORDS_DATA_DIR` and reuse it (re-login only on auth
errors). Debounced: at most one sync per 5 minutes, scheduled trailing
so the last add in a burst still gets synced. Disabled with
`ECHOWORDS_ANKI_SYNC=false`; a sync failure (network, AnkiWeb down) is
logged at warning level, retried on the next debounce tick, and never
affects the status line. **Safety rule:** if `sync_collection` reports
that a one-way full sync is required (diverged collections), never
resolve it automatically — log an error and surface it in `/api/status`
(M7); a full upload could clobber the user's other decks. The only
automatic full transfer is the first-run full **download** (bootstrap,
spike above).

Tests: use a **real temporary `Collection`** (pylib is a local library —
no network, no GUI; the "no real network in tests" rule is satisfied)
and mock only the sync calls. Assert: note-type bootstrap creates both
card templates; a pre-existing note type whose fields or template names
differ fails with the misconfigured-model error and adds nothing;
per-language deck creation and deck-scoped dedup
(same word in two decks is not a duplicate); single- and multi-meaning
rendering of `Translations` and `Meanings`; gapped-example masking —
exact match masked, every occurrence in the sentence masked, a
multi-word phrase masked as one gap, an inflected form falling back to
`pos`, an empty `pos` falling back to translations alone, and no
unmasked example ever emitted into `Translations`; HTML escaping of
payload values; media naming/hashing and the `[sound:...]` reference using the
name returned by `add_file`; lookup-only skip; sync debounce (fake
clock), hkey persistence/reuse, the `ECHOWORDS_ANKI_SYNC=false` no-op,
and the full-sync-required → error-not-auto-resolve path; error
propagation.

### M6 — pronunciation audio

`audio.py`: `async def fetch_pronunciation(word: str, lang: Language) -> Path | None`,
a three-step chain driven by the language config, where each step falls
through to the next on ANY exception (log at warning level, never raise):

1. **Dictionary recording** — dictionaryapi.dev at the language's
   `dict_api` code (English accent preference; skipped entirely for
   languages with no `dict_api`, e.g. Serbian), first non-empty audio URL,
   download mp3 to `ECHOWORDS_DATA_DIR/audio/`. Skipped for multi-word
   input.
2. **Local TTS** — **Piper** (`piper-tts`) with the language's
   `tts_voice`. Skipped entirely when the language's `tts` is `edge`
   (Serbian — no usable local voice exists; see `spec/decision-tts.md`,
   and never be tempted by `sr_RS-serbski_institut`: it is Lower
   Sorbian, not Serbian). Voice downloads are **config-driven**: only
   the configured Piper voices (`.onnx` + `.onnx.json`) are downloaded
   into `ECHOWORDS_DATA_DIR/models/` by a background task started at
   app startup, NOT on first request, where the download would delay
   the first pronunciation. The download URLs (Piper voices from the
   `rhasspy/piper` voices repo) are pinned in code as constants with
   their SHA-256 checksums; verify the checksum before installing (log
   progress; a failed download or checksum mismatch must not corrupt
   the cache — download to a temp name, rename only after verification;
   retry on next startup). Until a language's files are in place this
   step reports "not ready" and the chain falls through to step 3. Run
   inference in `asyncio.to_thread` (CPU-bound). Piper outputs WAV →
   mp3 via `lameenc`. Import `piper` lazily at call time so a broken
   install degrades to step 3 instead of killing the app at startup —
   a sanctioned exception to the top-level-imports rule, the other being
   M2's llmbroker; mark it with a comment. Note the limit of this fall-through: it catches
   runtime **exceptions**, not an OOM kill — engines are sized to the
   1 GB host by config up front ("Deployment"), not left to degrade at
   runtime. First task of this milestone: on a clean machine check
   whether Piper phonemization needs the `espeak-ng` system library (it
   can); if so, document it in the README (M8) as an optional system
   requirement — without it the local engine falls through to edge-tts.
3. **edge-tts (online)** — the language's `edge_tts_voice`
   (or `ECHOWORDS_EDGE_TTS_VOICE` default), native mp3 output. Serbian's
   **primary** engine (its chain is effectively dictionary-skip →
   edge-tts) and the last-resort fallback for every other language. On
   failure return `None`.

Runs via `asyncio.create_task` in parallel with the LLM stream,
speculatively for the raw input; awaited only after generation ends, and
only with a bound — `asyncio.wait_for(task, ECHOWORDS_AUDIO_TIMEOUT)`
(default 20 s): on timeout cancel the task and proceed exactly as for
"no audio". The functional description requires that audio never delay
the text answer or the ~5 s card budget, and the await happens on the
single queue worker — an unbounded hang (edge-tts is known to wedge)
would stall the whole queue. Every httpx request inside the chain also
carries its own `timeout=10`.
Because autocorrection is advisory, the canonical word always equals the
input, so the speculative fetch is always the right one — it is used as
is, with no re-fetch in the normal flow. A re-fetch happens only when the
user taps the correction button (M7): that path re-processes the word for
the suggested spelling (same language), so neither the entry nor the card
ever carries audio of a typo the user did not accept. That is the one
case where audio arrives noticeably after the text. Delivery: the stored
mp3 is served by `GET /api/audio/{name}` (bare server-generated
filenames only — reject anything else); the `done` event carries the
URL, the page attaches an `<audio>` element (autoplay attempted, one-tap
replay always available); if no audio, the status line gains
"🔇 no audio". Tests: mocked httpx for the dictionary path (hit, miss,
HTTP error); a fake piper module (success, import failure, inference
failure) asserting per-language engine choice and fall-through order; a
`tts = "edge"` language (Serbian) skips step 2 and goes straight to
edge-tts; the voice-download task fetches only the voices present in
the config; monkeypatched edge-tts (success, failure → `None`); an
audio task that never finishes is cancelled at the deadline (use a
sub-second timeout in the test) and reports "🔇 no audio"; phrase input
skips the dictionary step; a Serbian word skips the dictionary step (no
`dict_api`); the normal flow uses the speculative result with no
re-fetch (canonical == input), and the correction-button re-process
(M7) fetches audio for the suggested word instead; the audio endpoint
serves a stored file and rejects a path-like name.

### M7 — the app's own features (two sessions: M7a, then M7b)

There is **no pending-card queue** in this design: the collection is
in-process (M5), so a card add cannot fail on connectivity; only the
AnkiWeb sync is asynchronous, and it retries by itself. **There is no
database either** — see the "Durable state" technology row. What M7 adds
is the history buffer, the stats/status endpoints, undo, the
correction button, the deeper-analysis control, the card rebuild, and the
word picker that turns a pasted phrase into a word plus its context.

That is twice the scope of any other milestone, so M7 is executed as
**two sessions in order**, each ending with its own green suite:
**M7a** builds the read-only surfaces plus undo — the history buffer that
everything else reads from, stats, status; **M7b** builds the four
controls that re-run or rewrite something — the correction switch, the
card rebuild, the deeper analysis, and the word picker. M7a is worth
running on its own and ships alone; nothing in M7b is reachable before it.
A "(M7)" reference anywhere else in this plan means the pair.

#### M7a — history, stats, status, undo

`history.py`: a bounded in-memory ring buffer (last ~50 entries) of
`Entry(entry_id, lang, word, action, analysis_html, audio_file,
suggestion, shown_spelling, context, detail_html, created_at)` where action is
`pending | added | duplicate | lookup | failed`, written on every
processed word and updated in place as it progresses; `word` always
holds the canonical word and `analysis_html` the sanitized analysis. The
whole dataclass is defined here, but `shown_spelling`, `context` and
`detail_html` are only written by M7b's controls and stay empty until
then; `suggestion` already arrives from M4 through the `done` event.
Alongside it, per-language counters for duplicate and lookup-only sends
since startup. Both are plain process state — no locking beyond the
single queue worker that mutates them, no I/O, nothing to migrate, and
nothing to back up.

Endpoints and behaviors:

- `GET /api/words/recent` — the ring buffer, newest first; each entry
  carries word, language, sanitized HTML, status, audio URL, and — when
  the correction state still knows it — the suggestion and which
  spelling is shown. In-progress entries carry the text accumulated so
  far (M3).
- `GET /api/status` — per configured language: its deck, the paid alias its
  step-up would use, and **backend health** — one `await broker.snapshot()` for `llmbroker`
  and `api` alike: `providers_usable` of `providers_total`, the
  `degraded` flag (one quota left, nothing to fail over to),
  `missing_keys` for the pool and `direct_missing_keys` for the declared
  paid models, each carrying the `help` text saying where to get the
  key. Plus the day's paid-call count against
  `ECHOWORDS_API_DAILY_CAP` and whether the second step is still available at
  all today (M2). Each language is annotated
  with the outcome and time of its last LLM call and **which model
  answered it** — `handle.llm_name` from the pool call (M2), kept in
  memory; for an `api` language the configured alias, since a direct
  call is not journaled and names no routed model. Because that memory
  is empty after a restart, back it with
  `await broker.stats(operation=f"{prefix}-{lang.code}", since=…)` —
  per-model call counts for this language's own operation label, read
  from **llmbroker's** own journal in its home directory (not storage
  echo-words maintains — the app still keeps no database of its own),
  which outlives a restart and, like `snapshot()`, never provisions the
  pool or spends a request. No live
  LLM probe: status must answer instantly; `snapshot()` reads local
  state only (its
  `providers_usable` / `providers_total` / `degraded` / `missing_keys` /
  `direct_missing_keys` are exactly the fields named above). Plus
  AnkiWeb sync state: last sync result and time,
  whether unsynced local changes are waiting (`col.sync_status`), and a
  prominent error when a required one-way full sync is pending manual
  resolution (M5's safety rule).
- `GET /api/stats` — words added today / last 7 days / all time per
  source language, **counted from the collection**, not from a log of
  our own: `col.find_notes(f'deck:"{deck}" note:EchoWords')` and then
  bucket the returned note ids, which in Anki *are* creation
  timestamps in milliseconds. That makes the numbers correct across
  restarts and impossible to drift from the deck they describe. Run it
  in `asyncio.to_thread` like every other pylib call. Duplicate and
  lookup-only sends create no note, so those two counters come from
  `history.py` and the response marks them as counted **since
  startup** — the UI must label them that way rather than implying an
  all-time figure.
- `POST /api/languages/{code}/undo` — remove the note the last
  submitted word **of that language** produced (`col.remove_notes`),
  trash its media file in the collection
  (`col.media.trash_files([name])`, using the media name stored with
  the undo state — M5), and delete its cached audio file in
  `ECHOWORDS_DATA_DIR/audio/`; confirm with the word name. When the
  language's undo state records an action of `duplicate` or `lookup`
  the last word produced no note of ours, so undo replies "nothing to
  undo" and touches nothing — deleting the note found under that word
  would destroy a note that existed before the send.

Undo state (last word, its action — `added | duplicate | lookup` — its
note id when one was added, its media name, and the lookup flag) is per
source language, lives in memory and is lost on restart — documented
behavior.

Views: `StatsView` and `StatusView` (see "Module layout"), plus the
history rendering in `AddView` that until now showed only the live
entries.

Tests: stats windows bucketed from note ids against a temporary
collection, with the per-language breakdown and the since-startup
counters kept separate; the history buffer evicts oldest-first at its
bound, updates an entry in place rather than appending a second one,
and serves in-progress entries with their partial text; undo removes
the note, trashes its collection media file and deletes its cached
audio file; undo after a duplicate or a lookup-only send is a no-op
that reports nothing to undo; the undo state machine per language;
status rendering (pool snapshot degraded/healthy, pool and direct
missing keys, api daily-cap count and whether the paid step is still
available today, last model that answered, the per-language `stats()`
fallback after a restart, ok / unsynced-changes / full-sync-required
error).

#### M7b — correction switch, card rebuild, deeper analysis, word picker

Four controls, one shared shape: each re-runs an LLM call for an entry
that already exists, through **the same FIFO queue worker** (M3) so it
never races an in-flight submission, and each streams into the original
entry via `reuse_entry` rather than creating a second one. Three of them
touch the deck; the deeper analysis deliberately does not.

- `POST /api/words/{entry_id}/rebuild` — re-run **that entry's** word on the
  paid model, carrying the entry's context when it has one, preserving its
  lookup-only flag, and streaming into the existing entry (`reuse_entry`,
  M3). Before adding the new note, remove the previous run's result exactly
  like undo does: without the removal the duplicate check would block the
  replacement ("already in Anki") and the weak card would survive. The audio
  is not re-fetched — the word has not changed. Refused with a reason when
  no paid alias is configured or the daily cap is spent; the existing entry
  and its note are then left exactly as they were.
- `POST /api/words/{entry_id}/detail` — the deeper analysis. Runs the
  **extended prompt** (see "The extended prompt") on the paid model — the
  language's `api_model` or `ECHOWORDS_API_MODEL`, never the pool, because
  the user asked for the better model by name — carrying the entry's
  context when it has one. Its deltas are published as `detail` events and
  **appended below** the entry's analysis, which is left exactly as it was,
  as are the note and the audio: this control never touches the deck. The
  text is sanitized and cut at the `===CARD===` delimiter like any other
  answer (a model may emit a payload out of habit), and kept on the entry
  as `detail_html` — so the call is **idempotent**: a second request for an
  entry that already has one returns the kept text and pays nothing.
  Refused with a reason when no paid alias is configured or the daily cap
  is spent (the same one counter as every other paid call, M2) — never
  silently answered from the pool.
- `POST /api/words/{entry_id}/switch` — the correction button, below.
- **The word picker** — client-side, in `AddView`. A submission whose text
  holds more than one word is never sent as a word: the app renders the
  phrase's words as tappable choices and sends nothing until one is
  tapped. The tapped token becomes `word` (surrounding punctuation
  stripped) and the whole phrase becomes `context` in the same `POST
  /api/words` body; the tapped word is validated server-side exactly as a
  typed one (M1), so a token that fails gets the same short hint. A
  leading `?` is the lookup-only shortcut and is stripped before the split
  (M1's normalization), never offered as a choice, and the flag rides
  along with whichever word is tapped. This is also where the iOS
  share-sheet path lands: shared text arrives as a phrase and the picker
  is what turns it into a word.

**Correction button (advisory autocorrection).** When a processed word
came back with a usable `suggestion` different from the input (M4), the
`done` event carried it and the UI shows the button. `POST
/api/words/{entry_id}/switch` re-processes the word for the *other*
spelling (input ↔ suggestion) and replaces the note exactly the way a
rebuild
does — remove the previous run's result (`col.remove_notes`,
`col.media.trash_files`, the cached audio file), then run the full
pipeline (LLM analysis, audio fetch, add) for the chosen word, through
the same word queue so it never races an in-flight submission. The
re-run streams **into the original entry** (`reuse_entry`, M3) — no
second entry ever appears; only the audio for the new spelling arrives
as the entry's new pronunciation. The lookup-only flag is preserved (a
lookup-only request stays card-less on switch — only the analysis and
audio change). After the switch the button flips to offer the reverse
("↩︎ Вернуть «recieve»"), so it is reversible both ways. The decision
state lives in an in-memory map keyed by `entry_id` — input, suggestion,
language, lookup flag, which spelling is currently shown, and the
current note id plus its media name. After a switch, if the language's
undo state points at the note that was just replaced, update it to
the new note id, media name, and the spelling now shown — otherwise an
undo issued right after a switch would target a note that no longer
exists.

The correction decision state is per entry, lives in memory, and is lost
on restart — documented behavior; after a restart a switch, rebuild or
detail request on an old entry gets a "request expired" response instead
of acting on stale state.

Tests: a rebuild replaces the previous note, keeps the audio and streams
into the existing entry; a rebuild refused by the cap changes nothing;
the deeper analysis appends below the analysis instead of replacing it
and leaves the note and audio untouched, a second call returns the kept
text without a second paid call, a stray `===CARD===` block in its
answer is cut away, and a request refused (no alias / cap spent) leaves
the entry exactly as it was; the correction switch toggles
input↔suggestion and replaces the note (preserving the lookup-only flag
and flipping the label); the switch re-run reuses the original entry and
creates no new one; a switch updates the language's undo state when it
replaced the note that state pointed to; a stale/unknown entry id gets
the request-expired response instead of acting on any of the three
controls. Vitest for the picker: a multi-word submission renders one
choice per word and posts nothing until a tap, the tap posts the tapped
word with the whole phrase as `context`, a leading `?` sets the
lookup-only flag and never appears as a choice, and a single-word
submission goes straight through with no picker.

### M8 — PWA install, deploy tasks, release

- **Install bits**: the `manifest` (name, icons, standalone display)
  and icons; the service worker is generated by `vite-plugin-pwa` from
  the config already in place since M1, so this step is assets and
  verification (home-screen install on iOS, an offline open of the
  shell, `/api/*` never served from cache) rather than new plumbing.
- **Local resend queue**: words whose `POST /api/words` failed (backend
  down, no connectivity) are stored client-side and re-sent
  automatically, in order, on the next app open or `online` event — the
  functional description's resilience behavior. Port dinary's
  `flushQueue` pattern (single in-flight guard, per-item error
  branching, stop-on-first-failure) reduced to one word per item.
  Vitest: items are re-sent in order, a failure stops the drain and
  keeps the remainder, a duplicate response drops its item.
- **Deploy tasks** (`tasks/`, ported from dinary — see "Deployment"):
  `setup-app`, `deploy --ref=…`, `status`, `logs`, `build-static`,
  plus `.deploy.example/.env` documenting every variable and a
  gitignored `.deploy/`. Verify on the real instance: `setup-app
  --with-host-prep` is re-runnable without damage, `deploy` gates on
  `/api/health`, the unit survives a reboot (the `tailscaled` wait loop
  is what makes this work), and the app answers over the tailnet from
  the phone at the node's root. Record echo-words's steady-state and
  peak RSS here and confirm the unit's `MemoryHigh`/`MemoryMax` match
  reality. Also confirm **dinary's replication still lands** on this
  box after the host-prep pass — it is the same machine that receives
  its Litestream files.
- **README**: the deploy flow above; the **Tailscale setup** (join,
  `tailscale serve --bg 8080`; the app is tailnet-only by design), "Add to
  Home Screen" on iOS, the optional iOS Shortcut that POSTs share-sheet
  text to `/api/words` (recipe, one paragraph), the `languages.toml`
  format and per-language decks, the AnkiWeb credentials setup
  (`ECHOWORDS_ANKIWEB_USER` / `_PASSWORD`; note the first-run full
  download of the existing collection and the self-hosted
  `ECHOWORDS_SYNC_ENDPOINT` fallback), the optional `espeak-ng` system
  dependency for Piper, and the **deployment target**: Oracle Free Tier
  `VM.Standard.E2.1.Micro` — 1 GB RAM, **swap file as a hard
  requirement** (2 GB), and the memory limits in the unit; note that
  the Arm `A1.Flex` shape, when a region actually has capacity, lifts
  the memory constraints. State plainly that the app keeps **no
  database and needs no backup**: only `ECHOWORDS_DATA_DIR` matters,
  its Anki collection is synced to AnkiWeb anyway, and history and
  counters are in-memory by design. Mention that `ECHOWORDS_DATA_DIR/audio/` keeps
  one small mp3 per looked-up word and has no cleanup policy in v0.1 —
  the files are safe to delete at any time, since the copy Anki reviews
  from lives in the collection's own media folder.
- Bump version to `0.1.0`. Ensure `ruff check` is clean and wired into
  CI. Do NOT push the `v0.1.0` tag — publishing is deferred until PyPI
  credentials are configured; note this in the README.

## Product decisions and scope

Every product question this plan depends on is already answered, with
the rationale, in `spec/decision-product.md` — one note per word, the
two cards it produces, advisory-only autocorrection, headless Anki, the
sequential queue, no database, the two LLM steps, and the final
out-of-scope list. Read it when a milestone makes you wonder whether a
behaviour is deliberate; do not re-open it.
