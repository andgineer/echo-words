# echo-words — Functional Description

The source of truth for *what* to build. Together with
`implementation-plan.md` this is the complete specification for the
project.

## Purpose

A personal vocabulary assistant. The user sends an English word or short
phrase to a Telegram bot and gets back, within seconds, a rich explanation
in Russian: translations, usage, origin, examples. At the same time a
compact flashcard is added automatically to the user's Anki collection
(synced to their devices via AnkiWeb), so every word looked up during the
day becomes review material with zero extra effort.

## System context

- **Telegram bot** — the only user interface (a self-hosted Mattermost
  server was evaluated and rejected — see `decision-chat-interface.md`).
  Personal use, but organised
  as a **supergroup with forum topics**, one topic per source language
  (e.g. English, Deutsch, Српски). A whitelist of Telegram user IDs gates
  *who* may use the bot (messages from anyone else are ignored silently);
  the topic a message lands in gates *which source language* it is — and
  therefore which Anki deck. A message in the group's General topic, or in
  any topic not mapped to a language, gets a short hint and no LLM call, so
  routing to a deck is always explicit and deterministic (auto-detecting the
  language of a single word is not reliable enough to trust with deck
  placement). Running as a group requires the bot's privacy mode to be
  disabled so it sees plain word messages (setup note in the README).
- **Backend** — a single headless service with two supported homes: the
  user's laptop, or a small always-on instance — an Oracle Cloud Free
  Tier micro instance (1 GB RAM + swap) is enough; the two differ only
  in configuration (notably which TTS engine voices English — see
  "Pronunciation audio" and the implementation plan's "Deployment
  profiles"). Nothing in it requires a GUI or a desktop application. It connects to
  Telegram via long polling, so no public IP, domain, or webhook is
  needed.
- **LLM** — a pluggable backend, selected via configuration (and, once
  more source languages are added, per language). Three kinds, all present
  from v0.1: a **direct free-tier model pool** via the author's
  `llmbroker` (many free, rate-limited models with automatic failover —
  a plain text→text call, no subprocess, faster; the default); an
  **optional paid frontier model** called directly through llmbroker's
  *direct client* (opt-in, never required — for hard languages or when the
  user wants top quality; the only frontier-quality backend that still runs
  on the small always-on instance, streaming like the free pool does); and
  a **CLI coding agent** under a flat-rate subscription (the same three as
  `news-recap`: Claude, Codex, Antigravity/Gemini) for analysis the pooled
  models can't do well — a marginal, laptop-only option. The free pool and
  the flat-rate agent are un-metered; the paid path is opt-in and its spend
  is capped with automatic fallback to the free pool, so **no metered API is
  ever required**. Which backend is the default, and whether harder source
  languages (e.g. Serbian) need the paid model, the coding agent, or
  web-grounded lookups, is settled by a benchmark that runs *before* the
  build (implementation plan, M0).
- **Anki** — a server-side Anki collection maintained by the backend
  itself through the headless Anki Python library (pylib) — no Anki
  application and no AnkiConnect run next to the backend. The backend
  adds notes to its own collection in-process and synchronizes it with
  **AnkiWeb**; the user reviews in AnkiDroid / AnkiMobile / Anki desktop
  exactly as before, syncing from AnkiWeb. (Decision record:
  `decision-spaced-repetition.md`.)

## Core flow

1. The user sends a word or short phrase (idiom, phrasal verb,
   collocation — anything that makes a valid flashcard) by posting it in
   the topic of its language. The topic determines the source language,
   and thus the deck. Prefixing the message with `?` ("? word") requests
   a lookup-only analysis: the answer and audio arrive as usual but no
   Anki card is created.
2. The bot validates the input against the topic language's allowed
   script (Latin with accented letters — café, naïve, Straße — for
   English and German; Latin or Cyrillic for Serbian), length within a
   small limit, not a command. Anything else — including a word posted in
   the General topic or a topic not mapped to a language — gets a short
   hint instead of an LLM call.
3. The bot immediately posts a placeholder message ("⏳ *word* …") so the
   user sees the request was accepted.
4. The LLM agent runs in streaming mode when it supports it (the
   default agent does). As text arrives, the bot edits the placeholder
   in place, within Telegram's message-edit rate limits. The first
   translations are visible within a few seconds; the full answer
   completes without a second message. Agents that cannot stream
   deliver the complete answer in a single edit instead.
5. Words are processed one at a time, in the order sent. A batch that
   accumulated while the backend was down (see "Resilience") drains
   sequentially — never as parallel LLM runs.
6. The LLM produces **both outputs in one generation**: the full
   explanation for Telegram and a compact card payload. The card payload
   is never shown to the user. The explanation uses light text
   formatting (bold for the headword, italics for examples).
7. In parallel with the LLM call (the input word is known before
   generation starts), the backend obtains pronunciation audio for the
   word/phrase (see "Pronunciation audio"). The **canonical word** — the
   key for the card, deduplication, statistics, and undo/redo — is
   always the **raw input**, never silently replaced. If the input looks
   misspelled the LLM does not swap it: it analyzes the word as typed and
   only *suggests* a correction (see "Autocorrection: advisory only"), so
   the speculative audio for the input is always the right one and is
   never re-fetched in the normal flow. A card therefore always carries
   the word the user actually sent — a correction is applied only when the
   user asks for it, one tap away.
8. When generation completes, the backend sends the pronunciation as a
   voice message in the chat, adds the note (with the audio attached) to
   the collection, and appends a status line to the analysis message:
   "✅ added to Anki" / "📌 already in Anki". The collection lives
   in-process, so adding a card cannot fail because "Anki is not
   running"; delivery to the user's devices happens via the debounced
   AnkiWeb sync (see "Anki cards").

## Analysis content (the Telegram answer)

The answer contains, in this order:

- **Translations into the target language** (Russian by default; the
  target language is an app-wide configuration setting), ordered by
  likelihood in everyday speech, each marked with part of speech and
  register (neutral / colloquial / formal / slang) where it matters.
- **IPA transcription.**
- **Usage notes**: typical collocations and prepositions, common
  confusions with similar words, countability/irregular forms when
  relevant.
- **Origin**: if the word was borrowed into English from another language,
  a short story of where it came from and how it traveled; otherwise a
  one-line note on origin. No forced etymology essays for native words.
- **Examples**: 2–4 short sentences from everyday contexts, each with a
  Russian translation.

Additional behavior:

- If the input looks misspelled, the answer analyzes the word **as
  typed** and adds a one-line suggestion ("✏️ Возможно: receive"). The
  correction is never applied automatically — the card is built for the
  word as typed, and an inline button lets the user switch to the
  suggested word (and back). See "Autocorrection: advisory only".
- For idioms and phrasal verbs: the meaning, literal vs figurative sense,
  and typical situations where it is used.
- The whole answer must fit in one Telegram message (4096 chars), so the
  style is compact.

## Autocorrection: advisory only

The bot never silently rewrites a word. Auto-applying a correction is
attractive for genuine typos but has an insidious failure mode: when the
LLM "corrects" a word the user actually meant (a rare word, a proper noun,
a dialectal or deliberately unusual form), the card looks correct yet is
wrong, and — because every card enters a spaced-repetition deck — the user
would drill the wrong word without noticing. Analyzing the word **as
typed** keeps the card's front equal to what the user sent, so a mistake is
visible on the very first review, not hidden.

Behavior — fixed, not configurable (there is no on/off setting):

- The LLM analyzes exactly the word the user typed. The **canonical word**
  is always the raw input.
- When the input looks like a typo, the LLM does **not** change it. It adds
  a short suggestion line to the answer ("✏️ Возможно: receive") and
  returns the suggested spelling as a separate field in the card payload
  (`suggestion`); when nothing looks wrong, the suggestion is empty and no
  button appears.
- A suggested spelling is **LLM output that can become a canonical word**
  — one tap makes it the word of a real card. It is therefore held to the
  same rules as typed input: a suggestion that would have been rejected
  had the user sent it is discarded and no button is offered.
- The card (and its audio) is built for the word as typed and added to
  Anki immediately, exactly as for any other word.
- When a suggestion exists, an **inline button** is attached under the
  message — **[✏️ Исправить на «receive»]**. Tapping it re-runs the whole
  analysis for the suggested word, replaces the note (delete + add, the
  same way `/redo` replaces a note), re-fetches audio for the corrected
  word, and flips the button to **[↩︎ Вернуть «recieve»]** — so switching
  is reversible in both directions. A lookup-only (`?`) request keeps its
  lookup-only flag when switched (still no card, just a re-analysis).
- The button acts on its own message and is remembered in memory only
  (like undo/redo state), so it stops working after a restart — acceptable
  for a personal tool.

## Pronunciation audio

Audio is a core feature, not an add-on: every word gets pronunciation
both in the chat and on the flashcard.

- **Scope**: only the word/phrase itself is voiced. Example sentences
  are never voiced — a final decision, not a deferral: cards must stay
  light and generation fast.
- **Source priority**: a real native-speaker recording from free
  dictionary sources when one exists (for the languages those sources
  cover — English, German; Serbian has none). When no recording exists
  (phrases, rare words, unsupported languages), generate audio with a
  free TTS engine, **local where a usable voice model exists** — local
  so that audio keeps working with no external service to break: Kokoro
  for English (on the laptop; the 1 GB micro instance uses Piper
  instead), Piper for German. Serbian has no usable local voice model
  at all (the decision record `decision-tts.md` documents why — the one
  model labeled Serbian is in fact Lower Sorbian), so Serbian audio
  comes from a free online TTS (Microsoft Edge neural voices via
  edge-tts) — acceptable because audio is generated once per word and
  stored with the card, so an outage only affects words added during
  it. If the chosen engine fails for any reason, the free online TTS is
  tried as a last resort for every language.
- **Delivery**:
  - Telegram: a short voice message right after the analysis, so the user
    hears the word immediately.
  - Anki: the audio is attached to the card front, so it plays during
    review.
- **Resilience**: audio lookup runs in parallel with the LLM call and
  must never delay or fail the text answer. Because the canonical word is
  always the raw input, the speculative audio is always the right one — no
  re-fetch in the normal flow. Audio is fetched again only if the user
  taps the correction button, which re-processes the word for the
  suggested spelling (see "Autocorrection: advisory only"); that is the
  one case where a voice message arrives noticeably later. If neither a
  recording nor TTS is available, the card and answer go out without audio
  and the status line says so.

## Anki cards

- **One note per word.** Usually the back carries a single meaning, but
  when meanings are genuinely unrelated (bank «банк» / bank «берег») the
  LLM splits the back into numbered meaning blocks — at most three —
  each with a short meaning label, its own translations, and its own
  examples. A word never produces more than one note, so a review shows
  the word once and asks for everything it means; two cards with an
  identical front (which the reviewer could not tell apart) can never
  exist.
- **Compact by design.** Recognition card — front: the word/phrase with
  IPA transcription and pronunciation audio; back: the meaning
  block(s) — label (when there is more than one), the top 2–4
  translations, plus 1–2 short examples. The long-form analysis
  (etymology, full meaning list) stays in Telegram only — cards must
  remain quick to review.
- **Reverse (recall) card.** Every note also produces a second card:
  front — the translations (with meaning labels when there are several
  blocks), each followed by one of that meaning's examples with the word
  masked out ("I received a ___ from Amazon yesterday", with its
  translation); back — the word/phrase with IPA and pronunciation audio.
  A bare translation often matches several words of the source language
  (посылка → parcel / package / shipment), and the reviewer cannot know
  which one is expected; the gapped example pins it down without giving
  the answer away. A meaning's example is used only when it contains the
  word exactly as the user typed it; when no example of that meaning does
  (an inflected form, a separable prefix), the meaning shows its part of
  speech instead — the front never carries an unmasked example. Each word
  is therefore reviewed in both directions, from the same single note.
- **One deck per source language**, set in the languages configuration
  (e.g. `English::Vocabulary`, `German::Vocabulary`,
  `Serbian::Vocabulary`). The topic the word was posted in determines the
  deck — there is no per-message deck switching, and the deck is never
  guessed from the word itself.
- **Duplicates**: keyed by the pair (source language, canonical word),
  case-insensitively — the same spelling in two languages (English *Hand*
  and German *Hand*) is two separate notes in two decks, never a
  duplicate. The check is scoped to the language's deck. If a note already
  exists in the collection, nothing is added or modified and the bot
  reports "already in Anki".
- **Sync**: after cards are added the backend synchronizes its collection
  (including media) with AnkiWeb, so new cards reach the user's devices
  (e.g. the phone) without manual action. Sync is debounced and retried;
  its failures are only logged and never affect the answer or the card
  status — the collection is a local file, so an added card is never
  lost: unsynced changes survive restarts and are delivered by the next
  successful sync. Can be turned off in configuration for setups without
  an AnkiWeb account.

## Bot commands

Kept minimal:

- `/start`, `/help` — what the bot does, how to use it (including the
  `?` lookup-only prefix and the ✏️ correction button for a suggested
  spelling).
- `/status` — agent health, AnkiWeb sync state (last result, whether
  unsynced changes are waiting).
- `/stats` — how many words were added today, over the last 7 days, and
  in total, plus how many sends were duplicates or lookup-only, broken
  down by source language (the same global report whichever topic it is
  called in).
- `/undo` — remove the note created by the last sent word from the
  collection (mistaken sends). When the last word created nothing — it
  was a duplicate or a lookup-only request — `/undo` reports that there
  is nothing to undo and changes nothing: it must never delete a note
  that existed before the last send.
- `/redo` — re-run the analysis for the last word (e.g. after a poor
  generation). The note from the previous run is replaced by the new
  one, so a bad card does not survive a redo. A lookup-only (`?`)
  request stays lookup-only on redo.

Everything else is plain text input. `/undo` and `/redo` act on the most
recent word **of the topic they are issued in** (i.e. per source
language) and only since the backend started — acceptable for a personal
tool.

## Non-functional requirements

- **Latency**: complete answer within ~20–30 s; card added within ~5 s
  after generation ends. Audio is fetched concurrently and must not
  extend these budgets. Incremental "first visible content within
  ~3–5 s" applies to **streaming-capable backends** — both llmbroker
  backends (the free pool and the paid direct client) and the Claude CLI
  agent. **Non-streaming backends** — the codex and antigravity agents —
  show only the placeholder until the full answer is ready, which is
  acceptable when the total stays inside the budget above.
- **Cost**: **no metered API is ever required.** By default LLM usage rides
  the free-tier `llmbroker` model pool or the existing flat-rate coding-agent
  subscription — neither is metered. A **paid per-token model is available as
  an opt-in backend** (`api`, via llmbroker's direct client) for hard
  languages or top quality; it is never the mandatory path, and its spend is
  bounded by a daily cap (`ECHOWORDS_API_DAILY_CAP`) that falls back to the
  free pool once reached. The design must run fully on un-metered backends;
  the metered backend only ever adds an optional quality tier.
- **Safety**: this concern applies to the **CLI coding-agent backend
  only**. Both llmbroker backends — the free pool and the paid `api` direct
  client — are plain text→text API calls: no shell, no filesystem, and no
  arbitrary network reach, so a hijacked prompt has nothing to exfiltrate
  with; the injection risk below is structurally absent for them (one more
  reason to prefer them where quality allows). For the coding-agent backend: user text is forwarded to a
  coding agent running under the user's own account on the backend host
  (the laptop or the user's cloud instance — the same invariant either
  way). The text is untrusted — a malicious or mistyped phrase that
  passes validation is **indirect prompt injection** (OWASP LLM01), and
  input validation is not a security boundary. The invariant: no input
  may ever cause the agent to read files, run commands, reach the
  network, or see the operator's environment secrets on the host.
  Prompt-level wording is a request, not a control; the boundary is what
  the agent process *can do* if the text hijacks it. This is enforced by
  each agent's **own** sandbox/permission controls — never by disabling
  them — breaking the exfiltration leg of the attack; an agent that
  cannot be restricted this way is dropped, not run unrestricted. See the
  implementation plan's "Agent hardening", grounded in `news-recap`'s
  agent-sandboxing research.
- **Resilience**: the backend host is not always on (a laptop, or a
  free-tier instance that may be reclaimed). Telegram keeps undelivered
  updates for 24 h, so words sent while the backend is down are processed
  when it starts — sequentially, one word at a time. The collection is a
  local file: cards added while AnkiWeb sync was failing survive
  restarts and reach the devices on the next successful sync.
- **Single instance, single user** (whitelist may hold a few family IDs).
  No horizontal scaling concerns.
- **Languages**: multiple **source** languages (each its own topic and
  deck), a single **target** language for all explanations and
  translations (Russian by default), both set in configuration. Adding a
  language is a config change (a new topic + a languages-table entry), not
  a code change.
- **Accent**: applies to English audio (dictionary recording choice and
  TTS voice), set per language in configuration; American by default.
  Never two recordings per card.

## Out of scope — final

These are decisions, not deferrals: webhooks, Docker, multiple **users**
with separate decks (multiple **source languages** with separate decks
for the single user ARE supported), example-sentence audio, any web UI.
