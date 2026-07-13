# wordgram — Implementation Plan

Execution handoff for the `wordgram` project. Read
`functional-description.md` first — it is the source of truth for
*what* to build; this plan says *how*. Where the two disagree, the
functional description wins.

## Where the work happens

Repository: `github.com/andgineer/wordgram`. It already contains the
0.0.1 scaffold: hatchling packaging with the version in
`src/wordgram/__about__.py`, `src` layout, pytest, `uv.lock`,
CI workflow (`.github/workflows/ci.yml`, runs `uv sync --frozen` +
`uv run pytest tests/`), and a publish workflow triggered by `v*` semver
tags. Build on top of it; do not restructure the packaging.

Rules:

- Python 3.12+. All imports at module top level. English-only comments
  and docs.
- Every new module gets tests in the same commit. `uv run pytest` must be
  green after every milestone.
- No real network, no real Telegram/Anki/agent in tests — fake or mock
  every boundary.
- Update `uv.lock` when adding dependencies (`uv lock`); CI uses
  `--frozen`.

## Technology choices (fixed)

| Concern | Choice |
|---|---|
| Telegram framework | `python-telegram-bot` v21+ (async, long polling) |
| HTTP client (AnkiConnect, dictionary) | `httpx` (async) |
| TTS (English, local) | Kokoro-82M via `kokoro-onnx` — local, Apache 2.0, near-natural English, faster than real time on CPU; nothing external to break. English only. Model (~300 MB) downloaded by a background task at startup into `WORDGRAM_DATA_DIR/models/` (see M6). Verify at M6 whether `kokoro-onnx` needs the `espeak-ng` system library for phonemization — if it does, it is a documented system requirement, not a hidden crash |
| TTS (non-English, local) | Piper (`piper-tts`, ONNX voices, MIT) — local neural TTS with per-language voices (German confirmed; verify a Serbian voice exists at M6, else that language falls through to edge-tts). Keeps the local-first resilience of the English path for de/sr. Voices downloaded at startup alongside the Kokoro model, same pinned-URL + checksum mechanism (M6). Piper also phonemizes via `espeak-ng` — the same optional system dependency as Kokoro |
| TTS (last resort) | `edge-tts` (MS Edge voices, free online, outputs mp3, per-language voices e.g. `de-DE-*`, `sr-RS-*`) — only when the local engine (Kokoro/Piper) fails or has no voice for the language; its known flakiness (unofficial API, recurring 403 breakage) is acceptable in this role |
| mp3 encoding | `lameenc` (pure-wheel LAME bindings) to convert Kokoro's / Piper's WAV output to mp3 — no ffmpeg system dependency |
| Dictionary pronunciation | `https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}` where `{lang}` is the source language's `dict_api` code (`en`, `de`, …; Serbian is unsupported → skip this step) — take the first `phonetics[].audio` non-empty URL (they are Wiktionary recordings); for English prefer entries whose URL contains the configured accent (`-us` / `-uk`), else any |
| Settings | `pydantic-settings`, env prefix `WORDGRAM_`, `.env` support |
| Persistent queue | stdlib `sqlite3`, single DB file |
| LLM | Pluggable backend behind one `stream_completion` seam (M2), **both kinds shipped in v0.1**, selected by config and by source language (from the languages table, M1): (a) **`llmbroker`** — the author's free-tier model-pool broker (`github.com/andgineer/llmbroker`): `AsyncBroker` over a pool of free, rate-limited models with automatic failover and quality-based routing, **no metered key** — a plain text→text call, so no subprocess, no agent sandbox, and much lower per-request latency than a coding agent; non-streaming (returns the full answer). (b) **CLI coding agent** — the same three as news-recap, `claude` / `codex` / `antigravity`, for what the pooled models can't handle. The **M0 spike (precedes M1)** benchmarks which backend is sufficient per language and how much faster llmbroker is, and sets the v0.1 default |
| Lint | `ruff` (line-length 99), run in CI after tests |

## Configuration (env vars)

| Variable | Meaning | Default |
|---|---|---|
| `WORDGRAM_BOT_TOKEN` | Telegram bot token | required |
| `WORDGRAM_ALLOWED_USER_IDS` | comma-separated Telegram user IDs | required |
| `WORDGRAM_TARGET_LANG` | language of all explanations and translations, app-wide | `ru` |
| `WORDGRAM_LANGUAGES_CONFIG` | path to the TOML table defining each source language (see "Languages configuration" below): topic id, deck, backend, dictionary code, TTS engine + voice, accent, allowed script | `~/.wordgram/languages.toml` |
| `WORDGRAM_GROUP_ID` | Telegram supergroup id the bot serves; messages from other chats are ignored | required |
| `WORDGRAM_LLM_BACKEND` | `llmbroker` or `agent` — fallback backend kind for a language whose table entry omits `backend` (default set by the M0 spike) | `llmbroker` |
| `WORDGRAM_AGENT` | when backend = `agent`: `claude`, `codex`, or `antigravity` | `claude` |
| `WORDGRAM_CLAUDE_CMD` | claude argv template | `claude -p {prompt} --model {model} --output-format stream-json --include-partial-messages --verbose --allowed-tools ""` (empty allow-list = nothing allowed; see "Agent hardening") |
| `WORDGRAM_CODEX_CMD` | codex argv template | `codex exec --model {model} --sandbox read-only -c model_reasoning_effort=low --output-last-message {out_file} {prompt}` |
| `WORDGRAM_ANTIGRAVITY_CMD` | antigravity argv template | `agy --model {model} -p {prompt}` — never with `--dangerously-skip-permissions`; see "Agent hardening" |
| `WORDGRAM_MODEL` | model substituted into the template | per agent: `sonnet` (claude — nuanced Russian linguistic analysis is worth more than haiku's latency on a flat-rate plan), `gpt-5.2` (codex), `gemini-3.5-flash` (antigravity) |
| `WORDGRAM_AGENT_TIMEOUT` | seconds | `120` |
| `WORDGRAM_AGENT_ENV_PASSTHROUGH` | CSV escape hatch: extra env var names allowed into the agent subprocess (see "Agent hardening") | empty |
| `WORDGRAM_LLMBROKER_CONFIG` | path to llmbroker's `llms.toml` (model pool); generate with `llmbroker preset freetier > llms.toml` | `~/.wordgram/llms.toml` |
| `WORDGRAM_LLMBROKER_OPERATION` | operation label passed to `ask`/`chat` so llmbroker tracks per-task quality and routes accordingly | `vocab` |
| `WORDGRAM_LLMBROKER_WEB` | allow the llmbroker backend a web-search tool for grounding (hard languages — see M0); off by default | `false` |
| `WORDGRAM_ANKI_URL` | AnkiConnect endpoint | `http://127.0.0.1:8765` |
| `WORDGRAM_ANKI_SYNC` | trigger AnkiConnect `sync` after additions (see M5) | `true` |
| `WORDGRAM_ACCENT` | `us` or `uk`, English dictionary-audio and voice choice; per-language override in the languages table | `us` |
| `WORDGRAM_TTS_VOICE` | default Kokoro (English) voice; per-language `tts_voice` in the table overrides | `af_heart` (us) / `bf_emma` (uk) |
| `WORDGRAM_EDGE_TTS_VOICE` | default last-resort edge-tts voice; per-language `edge_tts_voice` in the table overrides | `en-US-AriaNeural` (us) / `en-GB-SoniaNeural` (uk) |
| `WORDGRAM_DATA_DIR` | queue DB + downloaded audio | `~/.wordgram` |

## Languages configuration

`WORDGRAM_LANGUAGES_CONFIG` points at a TOML file with one entry per
source language, keyed by language code. It is the single source of truth
for everything that varies by language — deck, backend, audio, validation:

```toml
[languages.en]
topic_id   = 2                 # Telegram message_thread_id of the "English" topic
name       = "English"
deck       = "English::Vocabulary"
backend    = "llmbroker"       # llmbroker | agent; omit -> WORDGRAM_LLM_BACKEND
dict_api   = "en"              # dictionaryapi.dev code; omit if unsupported
tts        = "kokoro"          # kokoro | piper | edge (local engine; edge is also the fallback)
tts_voice  = "af_heart"
accent     = "us"              # meaningful for English
script     = "latin"           # latin | cyrillic | latin+cyrillic (input validation)

[languages.de]
topic_id  = 3
name      = "Deutsch"
deck      = "German::Vocabulary"
backend   = "llmbroker"
dict_api  = "de"
tts       = "piper"
tts_voice = "de_DE-thorsten-medium"
script    = "latin"

[languages.sr]
topic_id  = 4
name      = "Српски"
deck      = "Serbian::Vocabulary"
backend   = "agent"            # per the M0 spike, if the pool is insufficient for Serbian
# dict_api omitted — dictionaryapi.dev has no Serbian
tts       = "piper"            # verify a Serbian Piper voice exists at M6; else "edge"
tts_voice = "sr_RS-serbian-medium"
script    = "latin+cyrillic"
```

Semantics:

- **Routing.** An incoming message's `message_thread_id` is matched
  against `topic_id`. No match (General topic, or an unmapped topic) →
  short hint, no LLM call. The whitelist (`WORDGRAM_ALLOWED_USER_IDS`)
  still gates the sender independently.
- **Backend.** `backend` per language; absent → `WORDGRAM_LLM_BACKEND`.
  This replaces the old `WORDGRAM_BACKEND_BY_LANG` map — one place per
  language, not a separate parallel setting.
- **Audio.** `dict_api` (omit = skip the dictionary step), `tts` (which
  local engine — `kokoro` for English, `piper` elsewhere), `tts_voice`,
  and for the edge-tts fallback an optional `edge_tts_voice`; `accent`
  where it applies. See M6.
- **Validation.** `script` selects the allowed character set for the
  language (M1). Because the topic fixes the language before validation,
  the check is exact, not a guess.
- Config loads into a `Language` dataclass (new `languages.py`), looked up
  by `topic_id` (routing) and by code (backend/prompt). A missing file or
  a `topic_id` collision is a startup config error.

## Agent hardening

The bot forwards user text into a coding agent running under the user's
own account on the user's own laptop. Input validation (Latin letters,
~50 chars) is NOT a security boundary — "delete all files in home dir"
passes it, and a poisoned phrase is textbook **indirect prompt injection**
(OWASP LLM01): the prompt-level instructions in `prompt.py` are requests,
not controls; what matters is what the agent process *can do* if the text
hijacks it. The design target is the one `news-recap` settled on in
`spec/plan-agent-sandboxing.md` (findings verified 2026-07-13): break one
leg of the **lethal trifecta** (private data / untrusted content /
exfiltration) using each vendor's **own** built-in protection — preferring
the exfiltration leg — rather than a hand-built kernel sandbox. Probability
is low (a single whitelisted family member typing a word) but the blast
radius is irreversible (a leaked SSH key does not come back), so the
controls are cheap and proportionate: deny the agent file, shell, and
network tools, and do not build a custom sandbox unless a vendor's own
protection demonstrably fails.

wordgram has one advantage over news-recap. news-recap must deliver a
multi-KB prompt via a file (`{prompt_file}`), so it has to give each agent
a **read** tool to open it — its floor is "read-only". wordgram's prompt is
one short word passed as an argv positional (M2), never a file, so it needs
no tool at all — its floor is "**nothing allowed**".

Per agent (defaults in the config table; exact flag names may drift between
CLI versions — the M2 canary check below is the real gate):

- **claude — allow-list, not deny-list.** news-recap proved live (CLI
  v2.1.207) that `--allowed-tools "Read"` with no `--permission-mode` and
  no network tools is necessary and sufficient for its file-read flow;
  `dontAsk` / `bypassPermissions` are unneeded and `WebFetch` /
  `Bash(curl:*)` are pure exfil surface. An **allow-list is strictly
  better** than the deny-list this plan first sketched: a deny-list
  enumerates today's tools and silently permits any tool a future CLI adds.
  Because wordgram delivers the prompt via argv, not a file, it does not
  even need `Read`, so the default is `--allowed-tools ""` (nothing
  allowed). If the installed CLI rejects an empty allow-list, fall back to
  `--allowed-tools "Read"` — harmless here, since argv delivery never reads
  a file — which is exactly the value news-recap verified.
- **codex — read-only sandbox, no network flag.** codex's sandbox applies
  to the shell commands the agent spawns, not to codex's own model API call
  (made by the un-sandboxed launcher), so `--sandbox read-only` does **not**
  block codex from reaching its API — and a text→text task never needs the
  agent's shell to touch the network. That is why the default carries no
  `network_access=true`. (macOS Seatbelt has known network edge cases —
  codex#10390, #9298 — so confirm with one probe run in M2.)
- **antigravity — turn on agy's OWN sandbox, don't just omit the dangerous
  flag.** `agy` ships a native **Terminal Sandbox** (`sandbox-exec` on
  macOS, `nsjail` on Linux) plus a permission layer, configured in
  `~/.gemini/antigravity-cli/settings.json`: `enableTerminalSandbox` (bool,
  default **false**), `toolPermission` (`always-proceed` | `request-review`
  | `strict` | `proceed-in-sandbox`, default `request-review`), and
  `permissions.allow` / `permissions.deny` (e.g.
  `deny: ["command(curl)","command(wget)","command(rm -rf)"]`).
  `--dangerously-skip-permissions` is not merely "skip approvals" — it also
  auto-approves the *"bypass the sandbox"* prompt (antigravity-cli#36), so
  it specifically defeats agy's own protection; the default template must
  never carry it. agy has **no** read-only / plan mode for a
  non-interactive `-p` run (antigravity-cli#45, unresolved), so hardening
  agy means shipping the safe `settings.json` (`enableTerminalSandbox:
  true`, `toolPermission: proceed-in-sandbox`, deny-list for
  curl/wget/rm) — applied through a pipeline-owned config path so the
  operator's global settings file is never clobbered. If M2 finds agy
  cannot run headless under any setting that also contains it, drop agy
  from the supported list rather than run it unrestricted; the community
  fallback is a disposable Docker container with an egress allowlist and
  headless OAuth (`shelajev/agy-sbx-kit`), out of scope for v0.1.

**Environment hygiene (all agents).** The agent subprocess must not inherit
the operator's whole shell. Do not pass `os.environ.copy()`; build a
default-deny env — `PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `TMPDIR`, plus
the selected agent's own auth vars and the `WORDGRAM_*` settings — so an
unrelated secret in the shell (an API key, a token) can never reach a
hijacked agent. `WORDGRAM_AGENT_ENV_PASSTHROUGH` (CSV) is the escape hatch
for the rare extra var a specific setup needs.

## Module layout

```
src/wordgram/
  __about__.py      # version (exists)
  __init__.py       # exists
  config.py         # Settings
  languages.py      # Language dataclass + languages.toml loader; lookup by topic_id / code
  main.py           # entry point: build app, run polling; console_script `wordgram`
  bot.py            # handlers: whitelist filter, topic->language routing, commands, word messages
  streaming.py      # placeholder-edit loop bridging the backend stream -> Telegram edits
  backend.py        # stream_completion dispatcher: pick backend by lang (languages table), delegate
  agent.py          # CLI-agent backend: subprocess runner yielding text deltas
  llm_backend.py    # llmbroker backend: AsyncBroker ask/chat -> single-chunk yield
  prompt.py         # prompt template (source/target lang slots) + card-payload extraction
  card.py           # note dataclass (word, ipa, 1-3 meanings), validation of the LLM payload
  anki.py           # AnkiConnect client (add note, dedup, model/per-language deck bootstrap, delete, sync)
  audio.py          # per-language chain: dictionary + local TTS (kokoro/piper) + edge-tts -> mp3
  pending.py        # sqlite queue of notes not yet delivered to Anki + retry task
```

Add `wordgram = "wordgram.main:cli"` to `[project.scripts]`.

## The LLM contract (core of the system)

`prompt.py` builds one prompt per request from a template with two
language slots — the source language (from the topic, M1) and the target
language (`WORDGRAM_TARGET_LANG`). The `===CARD===` JSON contract below is
identical across languages; only the two slots and an optional
per-language morphology hint change:

```text
Ты помощник по изучению лексики. Язык слова — {source_lang}. Тебе дано
слово или короткая фраза на этом языке: {word}

Ответь на языке {target_lang}, компактно, без вступлений и без
завершающих фраз. {source_hints}
Структура ответа:

1. Первая строка: слово, транскрипция IPA, часть(и) речи.
2. Переводы — по убыванию частотности в обыденной речи, с пометами
   (разг., книжн., сленг, груб. и т.п.) там, где они важны.
3. Употребление: типичные сочетания и предлоги, с чем часто путают.
4. Происхождение: если слово заимствовано — 1-3 предложения о том, из
   какого языка и как пришло; для исконных слов — одна строка.
5. Примеры: 2-4 коротких предложения из повседневной жизни, каждое с
   переводом.

Если во входе похоже на опечатку — начни с «Возможно, вы имели в виду:
…» и разбирай исправленный вариант.
Если это идиома или фразовый глагол — объясни буквальный и переносный
смысл и типичные ситуации употребления.
Для выделения используй ТОЛЬКО HTML-теги <b> и <i>: разбираемое слово —
жирным, английские примеры — курсивом. Никакого markdown, никаких
других тегов.
Весь разбор — не длиннее 3500 символов.

После разбора выведи строку ровно ===CARD=== и сразу за ней JSON в одну
строку без пояснений и без HTML-тегов внутри значений:
{"word": "...", "ipa": "...",
 "meanings": [{"label": "...", "translations": ["...", "..."],
 "examples": [{"en": "...", "ru": "..."}]}]}
Обычно meanings содержит один элемент с пустым label. Раздели на
несколько (не более трёх) только если значения слова не связаны между
собой (как bank «банк» и bank «берег»); тогда label — помета в 1-3
русских слова, различающая значения. translations — 2-4 главных
перевода этого значения; examples — 1-2 самых коротких примера именно
этого значения.
```

`{source_lang}` / `{target_lang}` are the language display names, and
`{source_hints}` is an optional per-language line (e.g. for Serbian:
«для существительных указывай род и множественное число, для глаголов —
вид»); it is empty for languages that need no extra guidance. The prompt
prose stays in the operator's language; only the *answer* language is
`{target_lang}`, and `translations` in the card JSON are in that target
language.

Parsing rules (`prompt.py` / `card.py`):

- Everything before `===CARD===` is the Telegram text. During streaming,
  cut the displayed text at the delimiter as soon as any prefix of it
  appears at the end of the buffer (never flash `===CA` to the user).
- After the run, parse the JSON after the delimiter into a single
  `Note` (`word`, `ipa`, `meanings: list[Meaning]` where each meaning
  has `label` possibly empty, `translations: list[str]` non-empty,
  `examples: list[Example]`); reject an empty meanings list or more
  than three meanings. On any parse/validation failure: the Telegram
  answer still goes out, no note is created, status line says the card
  failed — never crash the handler.
- The payload's `word` field is the **canonical word**: together with the
  source language it is the key for the duplicate check (case-insensitive,
  scoped to the language's deck), the pending queue, `word_log`, undo/redo
  state, and the Anki `Word` field. The raw input is used
  only for the placeholder message and the speculative audio fetch
  (see M6) — when the LLM corrects a misspelling, everything downstream
  runs on the corrected word.

HTML safety (`streaming.py`): Telegram gets `parse_mode=HTML`, and the
LLM is only *asked* to emit `<b>`/`<i>` — the code must enforce it.
Sanitizer over the visible text: escape `&`, `<`, `>` everywhere except
whitelisted `<b>`, `</b>`, `<i>`, `</i>` tags; auto-close tags left
open at the current cut point (streaming can split a tag pair across
edits). If Telegram still rejects an edit with an entity-parse error,
retry that edit without `parse_mode` — degraded but delivered.

## Milestones

Each milestone = one or more commits, tests included, CI green. **M0 is the
exception**: it is a research spike whose harness lives in `experiments/`,
calls real models, and never enters CI — but it still lands as a commit (the
harness plus the decision doc) and it **precedes M1**, because its outcome
sets the v0.1 backend defaults the rest of the plan builds on.

### M0 — LLM backend spike (precedes M1–M8; decides the v0.1 backend defaults)

Runs **before** any product code. wordgram ships **both** backend kinds in
v0.1 (see the LLM technology row): `llmbroker` (free-tier model pool, fast,
no subprocess/sandbox) and the CLI coding agent (heavier, but frontier-tier
for what the pool can't do). M0 does not choose one *instead of* building the
other — the backend seam is built regardless (M2) — it measures **which
backend to default to, per source language, and whether llmbroker needs web
grounding for hard languages**, so M2 ships with the right `WORDGRAM_LLM_BACKEND`
and per-language `backend` defaults instead of a guess.

Why it must come first: the whole point of llmbroker here is that a plain
text→text call has *none* of the coding-agent overhead — no process spawn, no
agent bootstrap, no tool-permission machinery — and needs *none* of "Agent
hardening" (a chat completion can't read a file or run a command, so the
lethal-trifecta exfiltration leg is gone by construction). If llmbroker's
free-tier pool is good enough, it is both faster and simpler, and that should
shape the design from M1 — not be discovered after the CLI path is wired
everywhere.

**Hypotheses.**

1. **Sufficiency varies by source language.** The pooled free models may match
   the CLI agent's usefulness for *high-resource* source languages (English —
   the v0.1 target — and German) yet degrade for *lower-resource, morphology-heavy*
   ones (Serbian and similar: Cyrillic/Latin duality, case system): wrong
   lemmatization, invented etymology, weak register labels, unidiomatic
   examples, and — most consequential for us — malformed card JSON that
   `card.py` rejects.
2. **Speed.** Dropping the agent loop makes llmbroker materially faster.
   Quantify total latency (llmbroker is non-streaming, so measure to full
   answer, not first token) against the functional description's ~20–30 s
   budget and against each CLI agent — the expected win is llmbroker
   answering in a few seconds where the agent takes tens.
3. **Web grounding for hard languages.** The gap for hard languages may close
   only when the model is given internet access. llmbroker supports tool
   calling (`chat(tools=...)` / `run_tool_loop`), so grounding is a
   web-search tool wired into the llmbroker backend (`WORDGRAM_LLMBROKER_WEB`),
   not a jump to the CLI agent. Determine whether grounding is necessary,
   sufficient, or neither, per language.

**Method.**

- `experiments/backend_bench.py` (outside the package and CI — this harness
  deliberately hits real models; the "no real network in tests" rule stands
  for the shipped code). A fixed set of ~30–50 items per source language
  (English, German, Serbian) covering the shapes the prompt must handle:
  common and rare words, idioms/phrasal verbs, borrowed-etymology words,
  misspellings, and homonyms with genuinely unrelated meanings.
- Reuse the **exact** `prompt.py` template (with its source/target
  language slots filled per item) so we compare backends, not prompts. For each (backend × model × language) record: total latency,
  which model llmbroker's pool actually answered with (`reply.llm_name`),
  rate-limit/failover behaviour, and the raw analysis + `===CARD===` payload.
- Score against a rubric — a human pass by a Russian + source-language
  speaker, optionally with an LLM-judge as a pre-filter, never the final
  word: translation & register correctness, IPA plausibility, fact-checkable
  etymology, example naturalness, and card-JSON parse rate. Report per
  language, per model. Run the hard-language set twice — grounding off, then
  on — to isolate hypothesis 3.

**Deliverable: `spec/plan-llm-backend.md`** — the latency and quality numbers
per language/model, grounding on/off, and the resulting v0.1 defaults:
`WORDGRAM_LLM_BACKEND` (expected `llmbroker` for English), the per-language
`backend` values in the languages table for languages where the pool is not
sufficient (Serbian is the likely `agent` case), and whether
`WORDGRAM_LLMBROKER_WEB` defaults on for those. If the
spike finds the free-tier pool insufficient even for English, the v0.1 default
flips to `agent` and llmbroker stays a config-selectable option — but the
backend seam and both implementations still ship. This doc is an input to M2,
and it may amend the functional description's LLM/cost wording (llmbroker is
also un-metered, so the cost NFR holds either way).

### M1 — config + bot skeleton

`config.py`, `languages.py`, `main.py`, `bot.py`: application starts, long
polling in the configured supergroup (`WORDGRAM_GROUP_ID`), whitelist
filter on the sender (non-whitelisted updates are ignored, only
debug-logged), `/start` and `/help` reply with static text (help mentions
the `?` prefix and the one-topic-per-language layout). `languages.py`
loads `WORDGRAM_LANGUAGES_CONFIG` into `Language` objects indexed by
`topic_id` and code. Routing: a word message's `message_thread_id`
selects the language; the General topic or any unmapped topic gets a short
hint and no processing. Input validation is per the resolved language's
`script` (Latin incl. accented — café, naïve, Straße — for en/de; Latin or
Cyrillic for sr; plus spaces, hyphens, apostrophes; max ~50 chars;
otherwise a short hint). A leading `?` (with optional space) marks the
request lookup-only and is stripped before validation. Handler for a valid
word replies with a stub that names the resolved language. Tests: the
languages loader (topic/code lookup, missing file, duplicate topic id),
per-language validation incl. the `?` prefix and Cyrillic-vs-Latin per
language, topic routing (mapped / General / unmapped), whitelist filter
(use PTB objects directly, no live bot).

### M2 — LLM backend runner (llmbroker + CLI agent)

One seam, two backend kinds — both shipped here, defaults set by M0. The
handler calls `async def stream_completion(prompt, lang) -> AsyncIterator[str]`
(in a small `backend.py` dispatcher) which resolves the backend from the
language's `backend` field (`languages.py`) or, if absent,
`WORDGRAM_LLM_BACKEND`, and delegates:

- **`llmbroker` backend** (`llm_backend.py`): hold one module-level
  `llmbroker.AsyncBroker(WORDGRAM_LLMBROKER_CONFIG)`; per request
  `await broker.ask(prompt, operation=WORDGRAM_LLMBROKER_OPERATION)` (or
  `chat`/`run_tool_loop` with a web-search tool when `WORDGRAM_LLMBROKER_WEB`),
  and yield `reply.text` once — llmbroker is non-streaming, so this is a
  single-chunk yield, which the M3 bridge already handles (like the codex /
  antigravity plain path). No subprocess, no sandbox, no default-deny env:
  it is an HTTPS API call the operator already trusts, so "Agent hardening"
  does not apply to this backend. Map llmbroker's `NoLLMAvailableError`
  (whole pool rate-limited) and timeouts onto the same `AgentError` the
  bridge already knows, so the error path is uniform. Import `llmbroker`
  lazily so a missing/broken install degrades to a clear config error, not
  a startup crash. Optionally feed the parse outcome back via
  `reply.record_quality(...)` (a clean card JSON = good) so the pool
  self-tunes — noted, not required for v0.1.
- **CLI `agent` backend** (`agent.py`): unchanged from the original plan —
  spawns the agent selected by `WORDGRAM_AGENT` from its command
  template. Template handling: `shlex.split` the template FIRST, then
substitute `{model}`, `{prompt}`, and `{out_file}` inside individual
argv tokens with `str.replace` — substitution after splitting means
prompt content can never break quoting; no shell is involved.
`{out_file}` is a temp file path the runner always provides (only the
codex template uses it). The subprocess is spawned with a **default-deny
env** built here, not `os.environ.copy()` (see "Agent hardening"): the
allowlist plus `WORDGRAM_AGENT_ENV_PASSTHROUGH`, nothing else.

Three output parsers, chosen by agent:

- `stream-json` (claude): parse JSON-lines on stdout, yield text deltas
  from `stream_event`/`content_block_delta` events; if none arrived by
  process exit, fall back to the `result` event's full text as a single
  yield.
- `last-message` (codex): stdout carries codex's session header and
  reasoning noise, so it is ignored for content; after a zero exit, read
  the answer from `{out_file}` and yield it once. No incremental
  streaming for codex.
- `plain` (antigravity): yield decoded stdout chunks as they arrive. If
  the CLI buffers its output, the whole answer arrives as one late
  chunk — acceptable degradation, the streaming bridge (M3) handles it
  transparently.

Enforce `WORDGRAM_AGENT_TIMEOUT`: spawn with `start_new_session=True`
and on timeout kill the whole process group — agent CLIs spawn child
processes that a plain `kill()` on the parent would orphan — then raise
`AgentError`.
Non-zero exit, empty output, or missing/empty `{out_file}` →
`AgentError` with stderr tail in the message. Tests: fake agents = tiny
Python scripts in `tests/` — a stream-json one (happy path, no-deltas
path, nonzero exit, hang for the timeout path with a sub-second
timeout), a last-message one (writes the out file; also the
missing-out-file failure), and a plain one (chunked output, single-blob
output); plus template rendering tests proving `{prompt}` with
quotes/spaces/newlines survives intact for every default template. Also
test the env builder — seed a `FAKE_SECRET` and assert it is absent from
the built env, and assert the claude template's `--allowed-tools` is empty
(or exactly `Read`) and carries no `curl`/`WebFetch`, the codex template
has no `network_access`, and no template carries
`--dangerously-skip-permissions`. For the **llmbroker backend**: a fake
`AsyncBroker` (monkeypatched — no real pool) asserting the happy path yields
`reply.text` as one chunk, that `operation` is passed through, that
`NoLLMAvailableError` and a timeout both surface as `AgentError`, and that
the `backend.py` dispatcher picks the backend from the language's `backend`
field before falling back to `WORDGRAM_LLM_BACKEND`.

Closing this milestone requires the manual check from "Agent hardening" —
which applies **only to the CLI `agent` backend**; the llmbroker backend is a
plain text→text API call with no shell, file, or arbitrary-network reach, so
the containment canaries below are moot for it (there is nothing to contain) —
the only sanctioned manual step in the plan; real CLIs stay out of the
test suite. For each supported agent, run its default template once and
confirm two things: (1) a plain word generation completes with tools
disabled — for claude, that an empty `--allowed-tools ""` is accepted (else
fall back to `"Read"`); for codex, the single probe that `--sandbox
read-only` still lets it reach its API; for agy, that it runs headless
without hanging under `enableTerminalSandbox: true` + `toolPermission:
proceed-in-sandbox`. (2) The **containment canaries** hold, mirroring
news-recap's acceptance bar (`spec/plan-agent-sandboxing.md`, E3): feed a
prompt whose "word" is actually an injection payload and assert, on the
host, that a *read* canary (a file the payload tells the agent to read and
print) never appears in stdout; a *write* canary (payload tells the agent
to create `~/.ssh/probe`) is never written; a *network* canary (payload
tells the agent to `curl`/POST to a remote host) produces no egress; and an
*env* canary (a `FAKE_SECRET` seeded into the allowlisted env, which the
payload tells the agent to `echo`) never surfaces — proving the env
allowlist and the sandbox together. "Does it answer?" is necessary but not
sufficient; the canaries are the gate. An agent that cannot both answer and
pass all four canaries under a headless setting is dropped from the
supported list.

### M3 — streaming bridge

`streaming.py`: post placeholder "⏳ {word} …" in the word's topic
(`message_thread_id`), accumulate deltas, edit the message at most every
1.5 s and only when visible text changed
(remember: cut at delimiter, see LLM contract), passing every edit
through the HTML sanitizer (see LLM contract) with `parse_mode=HTML`.
Final edit with the complete text; append the status line placeholder
later (M5). On `AgentError`: edit the message to a short apology +
`/redo` hint. Truncate visible text at 4000 chars with an ellipsis.
Handle Telegram `RetryAfter`/`BadRequest("message is not modified")`
gracefully; entity-parse `BadRequest` → retry the edit without
`parse_mode`.

Word messages are processed strictly one at a time — a single global
`asyncio.Lock` around the whole word pipeline, spanning all topics (no
parallel LLM runs even across languages). After downtime Telegram
delivers up to 24 h of backlog in one burst; without the lock that
means parallel agent subprocesses and interleaved edit loops flooding
Telegram's rate limits. Each queued word still gets its own
placeholder immediately, so the user sees the backlog was accepted.
PTB processes updates sequentially by default (`block=True`), which
would hold back the placeholders too: build the application with
`concurrent_updates=True` so handlers start immediately, post the
placeholder *before* acquiring the lock, and let the lock serialize
the rest of the pipeline.

Tests: fake `Message.edit_text` recorder + scripted delta sequences;
assert edit cadence, delimiter cutting, truncation, error path;
sanitizer cases — stray `<`/`&`, disallowed tags escaped, `<b>` split
across two deltas, unclosed `<i>` auto-closed at the cut; two words
sent together → second agent run starts only after the first pipeline
finishes.

### M4 — card extraction

`card.py` + prompt module: parse the payload per the LLM contract.
Tests: valid single-meaning payload, valid multi-meaning payload (2-3
meanings with labels), payload with trailing garbage, missing
delimiter, malformed JSON, empty translations, empty meanings list,
four meanings (rejected).

### M5 — Anki integration

`anki.py`, httpx-based AnkiConnect client (`version`, `createDeck`,
`modelNames`, `createModel`, `findNotes`, `addNote`, `deleteNotes`,
`storeMediaFile`, `sync`). On startup (lazily, first use): ensure the note type `Wordgram` exists
and, on first use of a language, that language's deck (from the languages
config) exists. Note type fields: `Word`, `IPA`,
`Translations`, `Meanings`, `Audio`; two card templates:

- **Recognition** — Front: `{{Word}} {{Audio}}<br>{{IPA}}` (the
  functional description puts IPA on the front — it describes the
  word's form, not the answer), Back: `{{Meanings}}`.
- **Recall** — Front: `{{Translations}}`, Back:
  `{{Word}} {{Audio}}<br>{{IPA}}<hr>{{Meanings}}`.

Minimal CSS. `Translations` and `Meanings` are rendered by the backend
from the parsed payload. `Translations`: one line per meaning — label
in bold (only when the note has more than one meaning) followed by
that meaning's translations; no examples, so the recall front never
gives the answer away. `Meanings`: one block per meaning — label in
bold (same condition), translations on one line, examples in italics
with their Russian translations — numbered `<ol>`-style when there is
more than one block. Every payload value is HTML-escaped before being
wrapped in tags: Anki fields are HTML, and the prompt only *asks* the
LLM to keep tags out of JSON values — a stray `<` or `&` must not
break the card.

One word = one note, so the first field (`Word`) is naturally unique
and Anki's own `addNote` duplicate rejection never fires against our
own notes. Duplicate check before adding: `findNotes` with query
`deck:"{deck}" note:Wordgram "Word:{word}"` — `{deck}` is the language's
deck and `{word}` the canonical word from the payload; case-insensitive
match is Anki's default. Scoping by deck is what lets the same spelling
exist in two languages without a false duplicate. If a note
exists, nothing is added and the send reports duplicate. Belt and
braces: an `addNote` "duplicate" error (a note added by hand between
check and add) is treated as the duplicate status, not as a failure.

`add_note(note, deck, audio_path)` (deck from the word's language) returns
`added(note_id) | duplicate`;
audio is sent once with `storeMediaFile` (filename
`wordgram-{slug}-{hash}.mp3`, where `slug` is the lowercased canonical
word with non-alphanumeric runs collapsed to `-` and `hash` is the
first 8 hex chars of the canonical word's SHA-1 — distinct phrases
that slugify identically, like "go over" vs "go-over", must not
overwrite each other's media) and referenced as `[sound:...]` in the
`Audio` field. Skipped entirely for lookup-only (`?`) requests —
status line "👁 lookup only". Wire into the handler after the final
edit: status line appended to the message. Track the last added note
id in memory for `/undo` and `/redo` (M7).

After every successful `addNote` (and after a queue drain, M7) the
client triggers AnkiConnect `sync` so new cards reach AnkiWeb and the
user's other devices. Debounced: at most one sync per 5 minutes,
scheduled trailing so the last add in a burst still gets synced.
Disabled with `WORDGRAM_ANKI_SYNC=false`; a sync failure (no AnkiWeb
account, network) is logged at warning level and never affects the
status line.

Tests: mock httpx transport; assert exact AnkiConnect payloads for
bootstrap (both card templates in `createModel`), per-language deck
creation and deck-scoped dedup, single- and
multi-meaning rendering of `Translations` and `Meanings`, HTML
escaping of payload values, audio reference and filename hashing,
lookup-only skip, addNote-duplicate-error → duplicate status, sync
trigger with debounce (and the `WORDGRAM_ANKI_SYNC=false` no-op), and
error propagation.

### M6 — pronunciation audio

`audio.py`: `async def fetch_pronunciation(word: str, lang: Language) -> Path | None`,
a three-step chain driven by the language config, where each step falls
through to the next on ANY exception (log at warning level, never raise):

1. **Dictionary recording** — dictionaryapi.dev at the language's
   `dict_api` code (English accent preference; skipped entirely for
   languages with no `dict_api`, e.g. Serbian), first non-empty audio URL,
   download mp3 to `WORDGRAM_DATA_DIR/audio/`. Skipped for multi-word
   input.
2. **Local TTS** — the language's `tts` engine: **Kokoro** (`kokoro-onnx`)
   for English, **Piper** (`piper-tts`) for the other languages, each with
   the language's `tts_voice`. All model files — Kokoro's
   `kokoro-v1.0.onnx` + `voices-v1.0.bin` and each configured Piper voice
   (`.onnx` + `.onnx.json`) — are downloaded into
   `WORDGRAM_DATA_DIR/models/` by a background task started at bot startup,
   NOT on first request, where the download would delay the first voice
   message. The download URLs (Kokoro GitHub release assets; Piper voices
   from the `rhasspy/piper` voices repo) are pinned in code as constants
   with their SHA-256 checksums; verify the checksum before installing
   (log progress; a failed download or checksum mismatch must not corrupt
   the cache — download to a temp name, rename only after verification;
   retry on next startup). Until a language's files are in place this step
   reports "not ready" and the chain falls through to step 3. Run inference
   in `asyncio.to_thread` (CPU-bound). Encode Kokoro's samples to mp3 with
   `lameenc`; Piper likewise outputs WAV → mp3. Import `kokoro_onnx` /
   `piper` lazily at call time so a broken install degrades to step 3
   instead of killing the bot at startup — the one sanctioned exception to
   the top-level-imports rule; mark it with a comment. First task of this
   milestone: on a clean machine check whether Kokoro **and** Piper
   phonemization need the `espeak-ng` system library (both can), and
   confirm a usable Serbian Piper voice exists — if none does, set
   Serbian's `tts` to `edge` and document it; if espeak-ng is needed,
   document it in the README (M8) as an optional system requirement —
   without it the local engine falls through to edge-tts.
3. **edge-tts (online, last resort)** — the language's `edge_tts_voice`
   (or `WORDGRAM_EDGE_TTS_VOICE` default), native mp3 output. On failure
   return `None`.

Runs via `asyncio.create_task` in parallel with the agent stream,
speculatively for the raw input; awaited only after the final edit.
If the canonical word from the card payload differs from the input
(case-insensitive compare) — the LLM corrected a misspelling — the
speculative result is discarded and `fetch_pronunciation` runs again
for the canonical word (same language — the topic fixes it): neither the
voice message nor the card may ever carry audio of a typo. This is the one case where audio arrives
noticeably after the text. Send to chat with `send_voice` (mp3
is accepted); if Telegram rejects it, fall back to `send_audio`; if no
audio, add "🔇 no audio" to the status line. Tests: mocked httpx for
the dictionary path (hit, miss, HTTP error); fake kokoro/piper modules
(success, import failure, inference failure) asserting per-language engine
choice and fall-through order; monkeypatched edge-tts (success, failure →
`None`); phrase input skips the dictionary step; a Serbian word skips the
dictionary step (no `dict_api`); a corrected word triggers a re-fetch and
the speculative result is ignored.

### M7 — pending queue, stats, and remaining commands

`pending.py`: sqlite (DB in `WORDGRAM_DATA_DIR`, survives restarts)
with two tables. The `word` column always holds the canonical word;
queries are a handful of tiny statements, so calling the stdlib driver
directly from async code is accepted — no thread offloading.

- `pending_notes(id, lang, word, note_json, audio_path, created_at)` — when
  `add_note` fails with a connection error, enqueue the note and set
  status "🕓 card queued". Background task retries the queue every
  60 s; before each delivery it re-runs the duplicate check
  (`findNotes`) and silently drops the entry on a hit — the note may
  have been added by hand or by an earlier entry while Anki was down.
  On success, edit nothing (the card just appears in Anki) but log;
  a drain that delivered at least one note triggers the debounced
  sync from M5.
- `word_log(id, lang, word, meanings_count, action, created_at)` where action
  is `added | duplicate | lookup`, written on every processed word —
  the source for `/stats`.

The handler's duplicate check (M5) is extended here: a word counts as
duplicate if a note exists in the language's deck OR a `pending_notes`
entry for the same (lang, word) is waiting — otherwise re-sending a word
while Anki is down would enqueue it twice and both copies would land after
the drain. Both paths compare (lang, canonical word) case-insensitively
(Anki's deck-scoped search already does; the sqlite lookup must too), and
they report
differently: a hit in Anki → "📌 already in Anki", a hit in the
queue → "🕓 already queued" — the status never claims a card is in
Anki when it is not.

Commands:

- `/status` — per configured language: its backend, model and deck; plus
  Anki reachable yes/no and the pending-queue size.
- `/stats` — words added today / last 7 days / all time, plus duplicates
  and lookups counts, broken down by source language (one global report,
  same in every topic).
- `/undo` — remove whatever the last sent word **in this topic** produced:
  delete its note via `deleteNotes` if it reached Anki, or delete its
  `pending_notes` row (together with its audio file in
  `WORDGRAM_DATA_DIR/audio/`) if it is still queued; confirm with the
  word name.
- `/redo` — re-run the last word **in this topic**, preserving its
  lookup-only flag and language. Before adding the new note, remove the previous
  run's result exactly like `/undo` does — `/redo` exists to fix a
  poor generation, and without the removal the duplicate check would
  block the replacement ("already in Anki") and the bad card would
  survive.

Undo/redo state (last word, its note id or pending row id, lookup flag) is
per topic (per source language), in memory, lost on restart — documented
behavior.
Tests: enqueue on connection error, retry drains queue and triggers
sync, retry re-checks duplicates and drops the entry, handler dedup
consults the queue case-insensitively and is scoped to (lang, word) so the
same spelling in two languages is not a duplicate and reports the queued
status, stats aggregation windows with per-language breakdown, undo removes
an added note, undo removes a
queued row together with its audio file, redo replaces the previous
note, undo/redo state machine.

### M8 — polish and release

README: install (`uv tool install wordgram` / `uvx wordgram`), required
env vars, the supergroup + forum-topics setup (one topic per source
language, disable the bot's privacy mode in BotFather so it sees plain
messages), the `languages.toml` format and per-language decks, AnkiConnect
setup pointer, the optional `espeak-ng` system dependency for
Kokoro/Piper, systemd/launchd hint (one paragraph, no unit files). Bump version to `0.1.0`. Ensure `ruff check` is clean and
wired into CI. Do NOT push the `v0.1.0` tag — publishing is deferred
until PyPI credentials are configured; note this in the README.

## Product decisions (all questions resolved — do not re-open)

- One note per word. Genuinely unrelated meanings (bank «банк» / bank
  «берег») become numbered blocks on the back — at most three, split
  by the LLM; usually one. Never separate cards: identical fronts
  would be indistinguishable during review, and one note per word
  keeps dedup, undo, and the queue trivially correct.
- Duplicate send → report only, existing note untouched: "📌 already
  in Anki" for a note in Anki, "🕓 already queued" for one still in
  the pending queue — the two are never conflated.
- The canonical word is the `word` field of the card payload — together
  with the source language, the key for dedup (deck-scoped), the queue,
  stats, undo/redo, and the Anki `Word` field, compared case-insensitively.
  The same spelling in two languages is two notes in two decks. When it
  differs from the raw input (the LLM corrected a misspelling),
  pronunciation audio is re-fetched for the canonical word and the
  speculative fetch is discarded.
- Every note produces two cards: recognition (EN→RU) and recall
  (RU→EN) — see M5. Still one note per word.
- Anki sync to AnkiWeb runs automatically after additions and queue
  drains, debounced; `WORDGRAM_ANKI_SYNC=false` turns it off.
- `?` prefix = lookup-only: analysis and audio, no Anki card.
- `/undo` covers queued notes; `/redo` replaces the previous run's
  note instead of being blocked by the duplicate check.
- Multiple source languages via **forum topics** (one topic per
  language), routed by `message_thread_id`; the topic determines the deck.
  One deck per source language from the languages config, no per-message
  switching and no guessing the deck from the word. A single target
  language for explanations (`WORDGRAM_TARGET_LANG`, Russian default).
  Language is never auto-detected — the topic is authoritative; the
  General/unmapped topic gets a hint, not a guess.
- Accent: config-level (`WORDGRAM_ACCENT` default, per-language override),
  applies to English audio, US default, one recording per card, no
  per-message choice.
- Telegram formatting IS in v0.1: HTML `<b>`/`<i>` only, enforced by
  the sanitizer, plain-text fallback on parse errors.
- Word/phrase audio only — example sentences are never voiced (final).
- `/stats` IS in v0.1 (see M7).
- v0.1 ships **two LLM backend kinds** behind one seam: `llmbroker` (the
  free-tier model pool — fast, no subprocess, no sandbox) and the CLI
  coding agent (`WORDGRAM_AGENT`: `claude` / `codex` / `antigravity`).
  Which one is the default, and which languages route to which, is fixed
  by the **M0 spike** (precedes M1) — not a guess and not deferred to a
  later version. This is *backend* selection, optionally per source
  language (the `backend` field in the languages table); it is NOT
  news-recap-style per-task routing tables, which a single-user bot still
  doesn't need.
- Agents run with tool execution denied via each vendor's **own**
  protection — claude allow-list (empty; `Read` fallback), codex
  `--sandbox read-only`, agy's own Terminal Sandbox settings — never
  `--dangerously-skip-permissions`, and never `os.environ.copy()` into the
  subprocess (default-deny env allowlist). Not optional: an agent that
  can't be restricted is dropped. Verified by containment canaries in M2,
  following news-recap's `spec/plan-agent-sandboxing.md` (see "Agent
  hardening").
- Words are processed sequentially (global lock), so a 24 h Telegram
  backlog drains one word at a time.

## Out of scope — final, not deferred

Webhooks, Docker, multiple **users** with separate decks (multiple
**source languages** with separate decks for the single user ARE in
scope), example-sentence audio, any web UI.
