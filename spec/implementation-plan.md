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
| HTTP client (dictionary pronunciation) | `httpx` (async) |
| Anki integration | **`anki` pylib, headless** (the non-GUI core of Anki as a PyPI package; manylinux x86_64 + aarch64 wheels, so it runs on Oracle Free Tier ARM). The backend maintains its own collection in `WORDGRAM_DATA_DIR/anki/` and syncs to AnkiWeb via pylib's `sync_login` / `sync_collection` / `sync_media`. Pin the version (`anki==26.5` at the time of writing) — pylib's API drifts between releases; upgrades are deliberate. No AnkiConnect, no Anki desktop, no GUI anywhere. Decision record: `spec/decision-spaced-repetition.md` |
| TTS (English, local — **laptop profile only**) | Kokoro-82M via `kokoro-onnx` — local, Apache 2.0, near-natural English, faster than real time on CPU; nothing external to break. English only. Model (~300 MB) downloaded by a background task at startup into `WORDGRAM_DATA_DIR/models/` (see M6) — only when some language actually configures `kokoro`. Does NOT fit the 1 GB micro profile (see "Deployment profiles"): there English uses Piper or edge-tts instead. Verify at M6 whether `kokoro-onnx` needs the `espeak-ng` system library for phonemization — if it does, it is a documented system requirement, not a hidden crash |
| TTS (local, both profiles) | Piper (`piper-tts`, ONNX voices, MIT) — local neural TTS with per-language voices, ~60–100 MB per voice, real time on Raspberry-Pi-class CPUs, so it runs even on the 1 GB micro instance. German confirmed (`de_DE-thorsten-medium`); English voices exist (e.g. `en_US-lessac-medium`) for the micro profile. **Serbian is settled: Piper has NO usable Serbian voice** — the only `sr_RS` dataset (`serbski_institut`) is actually **Lower Sorbian** (Sorbian Institute recordings miscatalogued under the Serbian locale) and must never be configured; Serbian's engine is edge-tts (decision record: `spec/decision-tts.md`). Configured voices downloaded at startup, pinned-URL + checksum mechanism (M6). Piper also phonemizes via `espeak-ng` — the same optional system dependency as Kokoro |
| TTS (online) | `edge-tts` (MS Edge neural voices, free online, outputs mp3, per-language voices e.g. `de-DE-*`) — the **primary** engine for Serbian (`sr-RS-SophieNeural` / `sr-RS-NicholasNeural`, near-commercial quality, both scripts; no usable local voice exists — see `spec/decision-tts.md`) and the last-resort fallback for every other language when the local engine fails. Its known flakiness (unofficial API, recurring 403 breakage) is acceptable in both roles: audio is generated once per word and stored in Anki media, so an outage only affects words added during it |
| mp3 encoding | `lameenc` (pure-wheel LAME bindings) to convert Kokoro's / Piper's WAV output to mp3 — no ffmpeg system dependency |
| Dictionary pronunciation | `https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}` where `{lang}` is the source language's `dict_api` code (`en`, `de`, …; Serbian is unsupported → skip this step) — take the first `phonetics[].audio` non-empty URL (they are Wiktionary recordings); for English prefer entries whose URL contains the configured accent (`-us` / `-uk`), else any |
| Settings | `pydantic-settings`, env prefix `WORDGRAM_`, `.env` support |
| Word log (stats) | stdlib `sqlite3`, single DB file |
| LLM | Pluggable backend behind one `stream_completion` seam (M2), **both kinds shipped in v0.1**, selected by config and by source language (from the languages table, M1): (a) **`llmbroker`** — the author's free-tier model-pool broker (`github.com/andgineer/llmbroker`): `AsyncBroker` over a pool of free, rate-limited models with automatic failover and quality-based routing, **no metered key** — a plain text→text call, so no subprocess, no agent sandbox, and much lower per-request latency than a coding agent; non-streaming (returns the full answer). (b) **CLI coding agent** — the same three as news-recap, `claude` / `codex` / `antigravity`, for what the pooled models can't handle. The **M0 spike (precedes M1)** benchmarks which backend is sufficient per language and how much faster llmbroker is, and sets the v0.1 default |
| Lint | `ruff` (line-length 99), run in CI after tests |

## Deployment profiles

One codebase, two documented ways to run it — the difference is **pure
configuration** (`languages.toml` + env), never a code path:

- **laptop** (incl. Apple Silicon): no memory pressure. English uses
  Kokoro, German uses Piper, Serbian uses edge-tts.
- **micro** — Oracle Cloud Free Tier `VM.Standard.E2.1.Micro`: **1 GB
  RAM**, 1/8 OCPU, x86_64. (The Arm `A1.Flex` shape — 2 OCPU / 12 GB
  for Always Free tenancies — is frequently unobtainable per region and
  is not assumed; if available it removes the constraints below.) A
  **swap file (1–2 GB) is a hard setup requirement**: PTB + Anki pylib
  + a Piper inference peak coexist in 1 GB only with swap behind them.
  **Kokoro is excluded by config on this profile** — its model +
  runtime does not reliably fit, and an OOM kill takes down the whole
  bot process, so the audio chain's exception-based fall-through (M6)
  never gets a chance; sizing engines to the host is the config's job,
  done ahead of time. English therefore uses Piper
  (`en_US-lessac-medium`) or edge-tts; German Piper; Serbian edge-tts.

Model downloads (M6) are driven by the config: only engines and voices
referenced by `languages.toml` are fetched, so the micro profile never
downloads the ~300 MB Kokoro model. Full engine rationale and the
comparison table: `spec/decision-tts.md`.

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
| `WORDGRAM_ANKIWEB_USER` | AnkiWeb account (email) for sync; required when `WORDGRAM_ANKI_SYNC` is on | required if sync on |
| `WORDGRAM_ANKIWEB_PASSWORD` | AnkiWeb password — used once to obtain the sync key (hkey), which is then stored in `WORDGRAM_DATA_DIR` and reused | required if sync on |
| `WORDGRAM_SYNC_ENDPOINT` | custom sync server URL (the self-hosted fallback from the decision doc); empty = AnkiWeb | empty |
| `WORDGRAM_ANKI_SYNC` | sync the collection to AnkiWeb after additions (see M5) | `true` |
| `WORDGRAM_ACCENT` | `us` or `uk`, English dictionary-audio and voice choice; per-language override in the languages table | `us` |
| `WORDGRAM_TTS_VOICE` | default Kokoro (English) voice; per-language `tts_voice` in the table overrides | `af_heart` (us) / `bf_emma` (uk) |
| `WORDGRAM_EDGE_TTS_VOICE` | default last-resort edge-tts voice; per-language `edge_tts_voice` in the table overrides | `en-US-AriaNeural` (us) / `en-GB-SoniaNeural` (uk) |
| `WORDGRAM_DATA_DIR` | Anki collection (`anki/`), word-log DB, TTS models, downloaded audio, stored sync key | `~/.wordgram` |

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
tts        = "kokoro"          # kokoro | piper | edge; laptop profile — on the 1 GB
                               # micro profile use "piper" (en_US-lessac-medium) or "edge"
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
tts       = "edge"             # no usable local voice: Piper's lone sr_RS model
                               # ("serbski_institut") is actually Lower Sorbian —
                               # never use it (spec/decision-tts.md)
edge_tts_voice = "sr-RS-SophieNeural"
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
  engine — `kokoro` for English on the laptop profile, `piper` for
  German and for English on the micro profile, `edge` for Serbian),
  `tts_voice`, and an optional `edge_tts_voice` (the edge-tts voice —
  primary for Serbian, fallback elsewhere); `accent` where it applies.
  Engine-per-profile rationale: `spec/decision-tts.md`. See M6.
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
  bot.py            # handlers: whitelist filter, topic->language routing, commands, word messages, correction-button callback
  streaming.py      # placeholder-edit loop bridging the backend stream -> Telegram edits
  backend.py        # stream_completion dispatcher: pick backend by lang (languages table), delegate
  agent.py          # CLI-agent backend: subprocess runner yielding text deltas
  llm_backend.py    # llmbroker backend: AsyncBroker ask/chat -> single-chunk yield
  prompt.py         # prompt template (source/target lang slots) + card-payload extraction
  card.py           # note dataclass (word, ipa, 1-3 meanings) + optional suggestion, validation of the LLM payload
  anki.py           # headless collection wrapper (pylib): open/bootstrap, add/find/delete notes, media, debounced AnkiWeb sync
  audio.py          # per-language chain: dictionary + local TTS (kokoro/piper) + edge-tts -> mp3
  word_log.py       # sqlite word_log (source for /stats)
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

Разбирай РОВНО введённое слово и НЕ подменяй его. Если оно похоже на
опечатку, не исправляй разбор: добавь короткую строку «✏️ Возможно: X»
и укажи X в поле suggestion карточного JSON. Если опечатки нет —
suggestion пустая строка.
Если это идиома или фразовый глагол — объясни буквальный и переносный
смысл и типичные ситуации употребления.
Для выделения используй ТОЛЬКО HTML-теги <b> и <i>: разбираемое слово —
жирным, английские примеры — курсивом. Никакого markdown, никаких
других тегов.
Весь разбор — не длиннее 3500 символов.

После разбора выведи строку ровно ===CARD=== и сразу за ней JSON в одну
строку без пояснений и без HTML-тегов внутри значений:
{"word": "...", "ipa": "...", "suggestion": "...",
 "meanings": [{"label": "...", "translations": ["...", "..."],
 "examples": [{"en": "...", "ru": "..."}]}]}
word — введённое слово как есть (не исправляй); suggestion —
предполагаемое исправление опечатки или пустая строка.
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
  than three meanings. Also read the optional `suggestion` string (a
  typo hint — see "Autocorrection: advisory only" in the functional
  description); it is transient UI state, not part of the stored note, so
  it is returned alongside the `Note`, not on it. A missing or empty
  `suggestion` means "no correction offered". On any parse/validation
  failure: the Telegram answer still goes out, no note is created, status
  line says the card failed — never crash the handler.
- The **canonical word is always the raw input**, never the LLM's output:
  autocorrection is advisory, so the payload's `word` merely echoes the
  input and is not trusted for identity. Together with the source language
  the raw input is the key for the duplicate check (case-insensitive,
  scoped to the language's deck), `word_log`,
  undo/redo state, the Anki `Word` field, and the speculative audio fetch
  (M6) — which is therefore always the right audio, with no re-fetch in
  the normal flow. `suggestion`, when non-empty and different from the
  input (case-insensitive), is the only thing that triggers UI: the
  streaming bridge attaches the inline correction button (M7). The
  corrected word runs downstream only if the user taps that button, which
  re-processes the word exactly as a fresh send for the suggested
  spelling.

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
later (M5). When the parsed payload carries a non-empty `suggestion`
that differs from the input (case-insensitive), the final edit also
attaches the inline correction keyboard (one button — the callback
handling and note replacement live in M7). On `AgentError`: edit the
message to a short apology + `/redo` hint. Truncate visible text at 4000 chars with an ellipsis.
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

`card.py` + prompt module: parse the payload per the LLM contract,
including the optional `suggestion` string returned alongside the `Note`
(absent, empty, and present-and-different cases). Tests: valid
single-meaning payload, valid multi-meaning payload (2-3 meanings with
labels), payload with trailing garbage, missing delimiter, malformed
JSON, empty translations, empty meanings list, four meanings (rejected),
payload with a `suggestion` and payload without one (both parse; the
suggestion never affects note validity).

### M5 — Anki integration (headless pylib)

**First task of this milestone — the sync spike** from
`decision-spaced-repetition.md` (a sanctioned manual step, like M2's
canaries; real AnkiWeb stays out of the test suite): with the pinned
`anki` version, live-verify the headless path end to end —
`sync_login(user, password, endpoint=None)` returns a usable
`SyncAuth`/hkey; a **fresh server collection bootstraps by downloading
the user's existing AnkiWeb collection** (never upload-over it — the
account already holds other decks); an added note with audio arrives on
AnkiDroid after `sync_collection(auth, sync_media=True)`. If the
AnkiWeb auth path fails on the current version, fall back per the
decision doc to the official self-hosted sync server
(`WORDGRAM_SYNC_ENDPOINT`) before touching the design.

`anki.py` wraps a headless `anki.collection.Collection` at
`WORDGRAM_DATA_DIR/anki/collection.anki2` (directory created on first
run; the bootstrap full-download above applies when sync is on). pylib
is blocking — run every collection call in `asyncio.to_thread`; the
global word-lock (M3) already serializes writers, and the process is
the collection's only writer by design. On first use: ensure the note
type `Wordgram` exists and, on first use of a language, that language's
deck (from the languages config) exists. Note type fields: `Word`, `IPA`,
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

One word = one note, so the first field (`Word`) is naturally unique.
Duplicate check before adding: `col.find_notes()` with query
`deck:"{deck}" note:Wordgram "Word:{word}"` — `{deck}` is the language's
deck and `{word}` the canonical word from the payload; case-insensitive
match is Anki's default. Scoping by deck is what lets the same spelling
exist in two languages without a false duplicate. If a note exists,
nothing is added and the send reports duplicate.

`add_note(note, deck, audio_path)` (deck from the word's language) returns
`added(note_id) | duplicate`;
audio is copied into the collection's media with `col.media.add_file`
under the name `wordgram-{slug}-{hash}.mp3` (where `slug` is the
lowercased canonical word with non-alphanumeric runs collapsed to `-`
and `hash` is the first 8 hex chars of the canonical word's SHA-1 —
distinct phrases that slugify identically, like "go over" vs "go-over",
must not overwrite each other's media; `add_file` may return an
adjusted name — use the returned name) and referenced as `[sound:...]`
in the `Audio` field. Skipped entirely for lookup-only (`?`) requests —
status line "👁 lookup only". Wire into the handler after the final
edit: status line appended to the message. Because the collection is
in-process, `add_note` cannot fail with "Anki is not running" — there
is no pending-card queue anywhere in the design. Track the last added
note id in memory for `/undo` and `/redo` (M7).

After every successful add the client schedules the **AnkiWeb sync**
(pylib: `sync_collection(auth, sync_media=True)`): on first need,
`sync_login(WORDGRAM_ANKIWEB_USER, WORDGRAM_ANKIWEB_PASSWORD,
endpoint=WORDGRAM_SYNC_ENDPOINT or None)`, then persist the returned
hkey in `WORDGRAM_DATA_DIR` and reuse it (re-login only on auth
errors). Debounced: at most one sync per 5 minutes, scheduled trailing
so the last add in a burst still gets synced. Disabled with
`WORDGRAM_ANKI_SYNC=false`; a sync failure (network, AnkiWeb down) is
logged at warning level, retried on the next debounce tick, and never
affects the status line. **Safety rule:** if `sync_collection` reports
that a one-way full sync is required (diverged collections), never
resolve it automatically — log an error and surface it in `/status`
(M7); a full upload could clobber the user's other decks. The only
automatic full transfer is the first-run full **download** (bootstrap,
spike above).

Tests: use a **real temporary `Collection`** (pylib is a local library —
no network, no GUI; the "no real network in tests" rule is satisfied)
and mock only the sync calls. Assert: note-type bootstrap creates both
card templates; per-language deck creation and deck-scoped dedup
(same word in two decks is not a duplicate); single- and multi-meaning
rendering of `Translations` and `Meanings`; HTML escaping of payload
values; media naming/hashing and the `[sound:...]` reference using the
name returned by `add_file`; lookup-only skip; sync debounce (fake
clock), hkey persistence/reuse, the `WORDGRAM_ANKI_SYNC=false` no-op,
and the full-sync-required → error-not-auto-resolve path; error
propagation.

### M6 — pronunciation audio

`audio.py`: `async def fetch_pronunciation(word: str, lang: Language) -> Path | None`,
a three-step chain driven by the language config, where each step falls
through to the next on ANY exception (log at warning level, never raise):

1. **Dictionary recording** — dictionaryapi.dev at the language's
   `dict_api` code (English accent preference; skipped entirely for
   languages with no `dict_api`, e.g. Serbian), first non-empty audio URL,
   download mp3 to `WORDGRAM_DATA_DIR/audio/`. Skipped for multi-word
   input.
2. **Local TTS** — the language's `tts` engine per the languages config:
   **Kokoro** (`kokoro-onnx`) or **Piper** (`piper-tts`), with the
   language's `tts_voice`. Skipped entirely when the language's `tts` is
   `edge` (Serbian — no usable local voice exists; see
   `spec/decision-tts.md`, and never be tempted by
   `sr_RS-serbski_institut`: it is Lower Sorbian, not Serbian). Model
   downloads are **config-driven**: only the files of engines and voices
   actually referenced by `languages.toml` — Kokoro's `kokoro-v1.0.onnx`
   + `voices-v1.0.bin` when some language configures `kokoro`, and each
   configured Piper voice (`.onnx` + `.onnx.json`) — are downloaded into
   `WORDGRAM_DATA_DIR/models/` by a background task started at bot startup,
   NOT on first request, where the download would delay the first voice
   message (the micro profile thus never downloads the ~300 MB Kokoro
   model). The download URLs (Kokoro GitHub release assets; Piper voices
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
   the top-level-imports rule; mark it with a comment. Note the limit of
   this fall-through: it catches runtime **exceptions**, not an OOM kill —
   on the 1 GB micro profile Kokoro must be excluded by config up front
   ("Deployment profiles"), not left to degrade at runtime. First task of
   this milestone: on a clean machine check whether Kokoro **and** Piper
   phonemization need the `espeak-ng` system library (both can); if
   espeak-ng is needed, document it in the README (M8) as an optional
   system requirement — without it the local engine falls through to
   edge-tts.
3. **edge-tts (online)** — the language's `edge_tts_voice`
   (or `WORDGRAM_EDGE_TTS_VOICE` default), native mp3 output. Serbian's
   **primary** engine (its chain is effectively dictionary-skip →
   edge-tts) and the last-resort fallback for every other language. On
   failure return `None`.

Runs via `asyncio.create_task` in parallel with the agent stream,
speculatively for the raw input; awaited only after the final edit.
Because autocorrection is advisory, the canonical word always equals the
input, so the speculative fetch is always the right one — it is used as
is, with no re-fetch in the normal flow. A re-fetch happens only when the
user taps the inline correction button (M7): that path re-processes the
word for the suggested spelling (same language — the topic fixes it), so
neither the voice message nor the card ever carries audio of a typo the
user did not accept. That is the one case where audio arrives noticeably
after the text. Send to chat with `send_voice` (mp3 is accepted); if
Telegram rejects it, fall back to `send_audio`; if no audio, add
"🔇 no audio" to the status line. Tests: mocked httpx for
the dictionary path (hit, miss, HTTP error); fake kokoro/piper modules
(success, import failure, inference failure) asserting per-language engine
choice and fall-through order; a `tts = "edge"` language (Serbian) skips
step 2 and goes straight to edge-tts; the model-download task fetches only
the files of engines/voices present in the config (a config with no
`kokoro` language downloads no Kokoro model); monkeypatched edge-tts
(success, failure → `None`); phrase input skips the dictionary step; a
Serbian word skips the dictionary step (no `dict_api`); the normal flow
uses the speculative
result with no re-fetch (canonical == input), and the correction-button
re-process (M7) fetches audio for the suggested word instead.

### M7 — stats and remaining commands

There is **no pending-card queue** in this design: the collection is
in-process (M5), so a card add cannot fail on connectivity; only the
AnkiWeb sync is asynchronous, and it retries by itself. What M7 adds is
the word log, the remaining commands, and the correction button.

`word_log.py`: sqlite (DB in `WORDGRAM_DATA_DIR`, survives restarts),
one table — `word_log(id, lang, word, meanings_count, action,
created_at)` where action is `added | duplicate | lookup`, written on
every processed word; the `word` column always holds the canonical
word. The source for `/stats`. Queries are a handful of tiny
statements, so calling the stdlib driver directly from async code is
accepted — no thread offloading.

Commands:

- `/status` — per configured language: its backend, model and deck; plus
  AnkiWeb sync state: last sync result and time, whether unsynced local
  changes are waiting (`col.sync_status`), and a prominent error when a
  required one-way full sync is pending manual resolution (M5's safety
  rule).
- `/stats` — words added today / last 7 days / all time, plus duplicates
  and lookups counts, broken down by source language (one global report,
  same in every topic).
- `/undo` — remove the note the last sent word **in this topic** produced
  (`col.remove_notes`), together with its cached audio file in
  `WORDGRAM_DATA_DIR/audio/`; confirm with the word name.
- `/redo` — re-run the last word **in this topic**, preserving its
  lookup-only flag and language. Before adding the new note, remove the previous
  run's result exactly like `/undo` does — `/redo` exists to fix a
  poor generation, and without the removal the duplicate check would
  block the replacement ("already in Anki") and the bad card would
  survive.

**Inline correction button (advisory autocorrection).** When a processed
word came back with a non-empty `suggestion` different from the input
(M4), the final edit (M3) carried a one-button inline keyboard. A
`CallbackQueryHandler` handles the tap: it re-processes the word for the
*other* spelling (input ↔ suggestion) and replaces the note exactly the
way `/redo` does — remove the previous run's result (`col.remove_notes`
plus the cached audio file), then run the
full pipeline (LLM analysis, audio fetch, add) for the chosen word, under
the same global word-lock so it never races an in-flight send. Audio is
fetched for the chosen word (this is the only re-fetch case, M6). The
lookup-only flag is preserved (a `?` request stays card-less on switch —
only the analysis and voice message change). After the switch the button
flips to offer the reverse ("↩︎ Вернуть «recieve»"), so it is reversible
both ways. `callback_data` is bounded to 64 bytes, so it carries only a
short token that keys into an in-memory map; the map holds the decision
state per correction message — input, suggestion, language, lookup flag,
which spelling is currently shown, and the current note id.

Undo/redo state (last word, its note id, lookup flag) is
per topic (per source language); the correction-button decision state is
per message (keyed by the button's `callback_data` token). Both live in
memory and are lost on restart — documented behavior; after a restart the
button reports that the request expired instead of acting on stale state.
Tests: stats aggregation windows with per-language breakdown, undo
removes the note and its audio file, redo replaces the previous
note, undo/redo state machine, `/status` sync-state rendering (ok /
unsynced-changes / full-sync-required error), the correction button
toggles input↔suggestion and replaces the note (preserving the
lookup-only flag and flipping the label), and a stale/unknown callback
token reports the request as expired instead of acting.

### M8 — polish and release

README: install (`uv tool install wordgram` / `uvx wordgram`), required
env vars, the supergroup + forum-topics setup (one topic per source
language, disable the bot's privacy mode in BotFather so it sees plain
messages), the `languages.toml` format and per-language decks, the
AnkiWeb credentials setup (`WORDGRAM_ANKIWEB_USER` / `_PASSWORD`; note
the first-run full download of the existing collection and the
self-hosted `WORDGRAM_SYNC_ENDPOINT` fallback), the optional `espeak-ng`
system dependency for
Kokoro/Piper, systemd/launchd hint (one paragraph, no unit files), and
the **two deployment profiles** ("Deployment profiles" section): the
laptop config (English via Kokoro) and the Oracle Free Tier
`VM.Standard.E2.1.Micro` config — 1 GB RAM, **swap file (1–2 GB) as a
hard requirement** (one-paragraph setup hint), English via Piper or
edge-tts, no Kokoro anywhere in `languages.toml`; note that the Arm
`A1.Flex` shape, when a region actually has capacity, lifts the memory
constraints. Bump version to `0.1.0`. Ensure `ruff check` is clean and
wired into CI. Do NOT push the `v0.1.0` tag — publishing is deferred
until PyPI credentials are configured; note this in the README.

## Product decisions (all questions resolved — do not re-open)

- One note per word. Genuinely unrelated meanings (bank «банк» / bank
  «берег») become numbered blocks on the back — at most three, split
  by the LLM; usually one. Never separate cards: identical fronts
  would be indistinguishable during review, and one note per word
  keeps dedup and undo trivially correct.
- Duplicate send → report only, existing note untouched: "📌 already
  in Anki".
- **Autocorrection is advisory only — hardcoded, no config flag.** The
  canonical word is always the **raw input** — together with the source
  language, the key for dedup (deck-scoped), stats, undo/redo,
  and the Anki `Word` field, compared case-insensitively. The same
  spelling in two languages is two notes in two decks. The LLM never
  silently swaps a misspelling: it analyzes the word as typed and returns
  an optional `suggestion`. When the suggestion differs from the input, an
  inline button under the message switches to the suggested word (and
  back), re-running the analysis and replacing the note like `/redo`; only
  that path re-fetches audio. Rationale: a silently swapped card looks
  correct but is wrong and would poison the spaced-repetition deck without
  the user noticing — analyzing as-typed keeps the card's front equal to
  what the user sent, so a mistake is visible on the first review. There
  is deliberately no on/off setting; this behavior is the design, not an
  option.
- Every note produces two cards: recognition (EN→RU) and recall
  (RU→EN) — see M5. Still one note per word.
- **Anki without a GUI — final.** The backend maintains its own
  collection via the headless `anki` pylib and syncs it to AnkiWeb;
  AnkiConnect and Anki desktop are not part of the architecture. There
  is no pending-card queue — adds are in-process and cannot fail on
  connectivity; only the sync retries. A required one-way full sync is
  never resolved automatically (protects the user's other decks).
  Evaluated alternatives (GetSpace, Mochi, own FSRS in chat, genanki):
  `spec/decision-spaced-repetition.md`.
- Anki sync to AnkiWeb runs automatically after additions,
  debounced and retried; `WORDGRAM_ANKI_SYNC=false` turns it off.
- `?` prefix = lookup-only: analysis and audio, no Anki card.
- `/redo` replaces the previous run's
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
- **TTS engines are settled by research, not deferred to M6**
  (`spec/decision-tts.md`): Serbian → edge-tts (Piper's lone `sr_RS`
  model is Lower Sorbian, not Serbian — never use it; no other usable
  free local voice exists); English → Kokoro on the laptop profile,
  Piper/edge on the 1 GB micro profile; German → Piper. Two deployment
  profiles (laptop / Oracle E2.1.Micro 1 GB + swap) differ only in
  config; model downloads follow the config.
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
- **Telegram is the chat interface — final.** Replacing it with a
  self-hosted Mattermost server was evaluated and rejected (extra
  always-on node instead of consolidation; inline buttons, voice
  messages, and mobile push degraded or paywalled in the free edition;
  a full ops stack for zero removed integration code). If chat is ever
  outgrown, the growth path is a Telegram Mini App, not a platform
  switch. Full analysis: `spec/decision-chat-interface.md`.

## Out of scope — final, not deferred

Webhooks, Docker, multiple **users** with separate decks (multiple
**source languages** with separate decks for the single user ARE in
scope), example-sentence audio, any web UI.
