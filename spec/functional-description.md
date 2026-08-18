# echo-words — Functional Description

The source of truth for *what* to build. Together with
`implementation-plan.md` this is the complete specification for the
project.

## Purpose

A personal vocabulary assistant. The user types or pastes a word or
short phrase in one of the configured source languages into a small web
app — a PWA pinned to the phone's home screen, or the same page in a
desktop browser — and gets back, within seconds, a rich explanation in
the target language (Russian): translations, usage, origin, examples.
At the same time a compact flashcard is added automatically to the
user's Anki collection (synced to their devices via AnkiWeb), so every
word looked up during the day becomes review material with zero extra
effort.

## Design goals

The four requirements every design decision is weighed against:

1. **Several source languages, one Anki deck per language.** Adding a
   language is a configuration change, never a code change.
2. **A maximally light backend whose home is an always-on Oracle Cloud
   Free Tier micro instance** (`VM.Standard.E2.1.Micro`, 1 GB RAM +
   swap). Anything that cannot run there is out of the design; the
   user's laptop is a development environment, not a deployment target.
   The backend keeps **no database of its own**: everything worth
   keeping is already in the Anki collection, so state that is not a
   card lives in memory and is expendable on restart.
3. **Rich, dictionary-beating explanations from an LLM.** A plain
   dictionary answer is not enough — that is the reason this project
   exists. Free models often struggle with Serbian; which model tier
   each language needs is settled by experiment (the M0 spike), not by
   assumption.
4. **LLM access goes through the author's own `llmbroker`** — its
   free-tier model pool for every answer, its paid direct client behind
   it for the times the pool is too slow and for what the user
   explicitly asks the better model to do. No metered API is ever
   required.

## System context

- **PWA — the only user interface.** A chat interface, whether a Telegram
  bot or a self-hosted Mattermost server, is rejected — see
  `decision-interface.md` and `decision-chat-interface.md`. A small app
  served by the
  backend itself: a source-language selector (the choice persists
  between visits), an input box, the streaming answer, playable
  pronunciation, and a history of recent words. Installed on the phone
  via "Add to Home Screen"; opened as a normal browser tab on the
  computer. The app is reachable **only inside the user's Tailscale
  tailnet**: `tailscale serve` publishes the backend's localhost port
  as HTTPS with an automatic certificate, and tailnet membership *is*
  the authentication — no login page, no auth code, no public exposure.
  Single user by design. On iOS the share sheet cannot target a PWA
  (Safari lacks Web Share Target); copy/paste works as anywhere, and
  the documented share-sheet path is a one-time iOS Shortcut that POSTs
  the shared text to the API over the tailnet.
- **Backend** — a single headless service whose home is an always-on
  micro instance (1 GB RAM + swap). It serves the API and the built PWA
  on a localhost port that Tailscale proxies; nothing else is exposed.
  No public IP, domain, or certificate management is needed. It stores
  **no database**: the Anki collection is the only durable state it
  keeps, alongside cached audio and voice models — everything else
  (recent answers, counters, undo state) is in-memory and expendable.
- **LLM** — one cascade, not a per-language choice. Both steps are plain
  streaming text→text calls through the author's `llmbroker`: the
  **free-tier model pool** (many free, rate-limited models with
  automatic failover) takes every request, and a **paid frontier model**
  via llmbroker's *direct client* stands behind it. The paid step is
  reached on latency — the pool did not finish the answer inside the
  budget — and on the two things the user asks the better model for by
  name: a deeper analysis, and rebuilding a card. The free pool is un-metered
  and the paid step is capped and optional, so **no metered API is ever
  required**. How good each step is per language was settled by a
  benchmark that ran *before* the build (implementation plan, M0).
- **Anki** — a server-side Anki collection maintained by the backend
  itself through the headless Anki Python library (pylib) — no Anki
  application and no AnkiConnect run next to the backend. The backend
  adds notes to its own collection in-process and synchronizes it with
  **AnkiWeb**; the user reviews in AnkiDroid / AnkiMobile / Anki
  desktop exactly as before, syncing from AnkiWeb. (Decision record:
  `decision-spaced-repetition.md`.)

## Core flow

1. The user picks the source language (the selector remembers the last
   choice) and submits a word or short phrase (idiom, phrasal verb,
   collocation — anything that makes a valid flashcard). A lookup-only
   request — the answer and audio arrive as usual but no Anki card is
   created — is made with the lookup-only control next to the input;
   prefixing the text with `?` ("? word") does the same as a typed
   shortcut.
   **A phrase instead of a word means context.** When the submitted text
   holds more than one word, the app does not guess which one is being
   asked about: it shows the phrase's words as tappable choices and the
   tapped one becomes the word. The whole phrase travels with it as
   context, and the analysis answers for *the sense used there* — which
   is the only way to reach a meaning that no dictionary lists, because
   it is a term of art, a joke, a regionalism, or simply rare. This is
   also what the iOS share-sheet path delivers: text shared from
   whatever the user was reading arrives as a phrase.
   Context never changes what the card is *about*: the canonical word is
   still the tapped word exactly as written, so deduplication, audio,
   statistics and the deck are unaffected by it.
2. The backend validates the input against the selected language's
   allowed script (Latin with accented letters — café, naïve, Straße —
   for English and German; Latin or Cyrillic for Serbian) and length
   within a small limit. Anything else — including a language code not
   present in the configuration — gets a short hint instead of an LLM
   call. The language is always the user's explicit selection, never
   guessed from the word (auto-detecting the language of a single word
   is not reliable enough to trust with deck placement).
3. The word immediately appears in the answer area as a pending entry
   ("⏳ *word* …"), so the user sees the request was accepted.
4. The LLM runs in streaming mode; the entry's text builds up live in
   place (delivered over a server-sent event stream). A backend that
   cannot stream shows the pending entry until the complete answer
   arrives at once.
   Every answer is asked of the **free pool first**. The request moves to
   the **paid model** when the pool does not deliver a *complete* answer
   within the latency budget — whether it never started or started at
   once and then kept going — and the user sees a slower answer, not an
   error; the pool being busy is the one thing the paid path exists to
   absorb. When the move happens mid-answer the partial text is
   discarded and replaced by the paid model's. Which model answered is
   visible on the entry; nothing else about the two paths differs, and
   the card is built from whichever answer arrived.
   **How fast the first token arrives is not a criterion and is never
   measured.** It is the easiest number in the system to look good on and
   the least related to what the user waits for: a model that emits one
   token immediately and the rest over a minute has answered slowly. Only
   the complete answer is judged, and streaming is a display choice —
   text appears as it is produced rather than in one jump — not a
   deadline of its own.
5. Words are processed one at a time, in the order submitted — never as
   parallel LLM runs.
6. The LLM produces **both outputs in one generation**: the full
   explanation for the answer view and a compact card payload. The card
   payload is never shown to the user. The explanation uses light text
   formatting (bold for the headword, italics for examples).
7. In parallel with the LLM call (the input word is known before
   generation starts), the backend obtains pronunciation audio for the
   word/phrase (see "Pronunciation audio"). The **canonical word** — the
   key for the card, deduplication, statistics, and undo — is
   always the **raw input**, never silently replaced. If the input looks
   misspelled the LLM does not swap it: it analyzes the word as typed and
   only *suggests* a correction (see "Autocorrection: advisory only"), so
   the speculative audio for the input is always the right one and is
   never re-fetched in the normal flow. A card therefore always carries
   the word the user actually sent — a correction is applied only when the
   user asks for it, one tap away.
8. When generation completes, the entry gains a playable pronunciation
   (one tap to hear; played automatically where the browser allows),
   the backend adds the note (with the audio attached) to the
   collection, and a status line is appended to the entry: "✅ added to
   Anki" / "📌 already in Anki". The collection lives in-process, so
   adding a card cannot fail because "Anki is not running"; delivery to
   the user's devices happens via the debounced AnkiWeb sync (see "Anki
   cards").

Finished and in-progress entries live in a server-side history (see
"UI actions"), so closing the app mid-generation, an interrupted event
stream, or opening the page on another device never loses an answer
while the backend is up.

## Analysis content (the answer)

The answer contains, in this order:

- **Translations into the target language** (Russian by default; the
  target language is an app-wide configuration setting), ordered by
  likelihood in everyday speech, each marked with part of speech and
  register (neutral / colloquial / formal / slang) where it matters.
- **Usage notes**: typical collocations and prepositions, common
  confusions with similar words, countability/irregular forms when
  relevant.
- **Origin**: if the word was borrowed into the source language from
  another language, a short story of where it came from and how it
  traveled; otherwise a one-line note on origin. No forced etymology
  essays for native words.
- **Examples**: 2–4 short sentences from everyday contexts, each with a
  Russian translation.

Additional behavior:

- If the input looks misspelled, the answer analyzes the word **as
  typed** and adds a one-line suggestion ("✏️ Возможно: receive"). The
  correction is never applied automatically — the card is built for the
  word as typed, and a button on the entry lets the user switch to the
  suggested word (and back). See "Autocorrection: advisory only".
- For idioms and phrasal verbs: the meaning, literal vs figurative sense,
  and typical situations where it is used.
- The answer stays compact (~3,500 characters at most) — it is a
  lookup, not an essay.

## Autocorrection: advisory only

The system never silently rewrites a word. Auto-applying a correction is
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
- When a suggestion exists, a button is attached to the entry —
  **[✏️ Исправить на «receive»]**. Tapping it re-runs the whole
  analysis for the suggested word, replaces the note (delete + add, the
  same way a rebuild replaces a note), re-fetches audio for the corrected
  word, and flips the button to **[↩︎ Вернуть «recieve»]** — so switching
  is reversible in both directions. A lookup-only request keeps its
  lookup-only flag when switched (still no card, just a re-analysis).
- The button acts on its own entry and is remembered in memory only
  (like the undo state), so it stops working after a restart —
  acceptable for a personal tool.

## Pronunciation audio

Audio is a core feature, not an add-on: every word gets pronunciation
both in the answer entry and on the flashcard.

- **Scope**: only the word/phrase itself is voiced. Example sentences
  are never voiced — a final decision, not a deferral: cards must stay
  light and generation fast.
- **Source priority**: a real native-speaker recording from free
  dictionary sources when one exists (for the languages those sources
  cover — English, German; Serbian has none). When no recording exists
  (phrases, rare words, unsupported languages), generate audio with a
  free TTS engine, **local where a usable voice model exists** — local
  so that audio keeps working with no external service to break: Piper
  for English and German (Piper's voices fit the 1 GB host). Serbian
  has no usable local voice model at all (the decision record
  `decision-tts.md` documents why — the one model labeled Serbian is in
  fact Lower Sorbian), so Serbian audio comes from a free online TTS
  (Microsoft Edge neural voices via edge-tts) — acceptable because
  audio is generated once per word and stored with the card, so an
  outage only affects words added during it. If the chosen engine fails
  for any reason, the free online TTS is tried as a last resort for
  every language.
- **Delivery**:
  - In the app: the pronunciation is attached to the answer entry —
    one tap to hear, replayable from the history.
  - Anki: the audio is attached to the card front, so it plays during
    review.
- **Resilience**: audio lookup runs in parallel with the LLM call and
  must never delay or fail the text answer. Because the canonical word is
  always the raw input, the speculative audio is always the right one — no
  re-fetch in the normal flow. Audio is fetched again only if the user
  taps the correction button, which re-processes the word for the
  suggested spelling (see "Autocorrection: advisory only"); that is the
  one case where the pronunciation arrives noticeably later. If neither a
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
  pronunciation audio; back: the meaning
  block(s) — label (when there is more than one), the top 2–4
  translations, plus 1–2 short examples. The long-form analysis
  (etymology, full meaning list) stays in the app only — cards must
  remain quick to review.
- **Reverse (recall) card.** Every note also produces a second card:
  front — the translations (with meaning labels when there are several
  blocks), each followed by one of that meaning's examples with the word
  masked out ("I received a ___ from Amazon yesterday", with its
  translation); back — the word/phrase with pronunciation audio.
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
  `Serbian::Vocabulary`). The language selected at submission determines
  the deck — there is no per-word deck switching, and the deck is never
  guessed from the word itself.
- **Duplicates**: keyed by the pair (source language, canonical word),
  case-insensitively — the same spelling in two languages (English *Hand*
  and German *Hand*) is two separate notes in two decks, never a
  duplicate. The check is scoped to the language's deck. If a note already
  exists in the collection, nothing is added or modified and the entry
  reports "already in Anki".
- **Sync**: after cards are added the backend synchronizes its collection
  (including media) with AnkiWeb, so new cards reach the user's devices
  (e.g. the phone) without manual action. Sync is debounced and retried;
  its failures are only logged and never affect the answer or the card
  status — the collection is a local file, so an added card is never
  lost: unsynced changes survive restarts and are delivered by the next
  successful sync. Can be turned off in configuration for setups without
  an AnkiWeb account.

## UI actions

Kept minimal — everything beyond typing a word:

- **About/help note** — what the app does, the lookup-only control and
  `?` shortcut, and the ✏️ correction button for a suspected typo.
- **History** — the answer area shows recent words with their finished
  analyses, pronunciation, and status; in-progress entries appear with
  their text accumulated so far. History is served by the backend, so
  it survives reloads, a dropped connection mid-generation, and
  switching devices — but it is held **in memory only** and starts
  empty after a restart. The cards it produced are unaffected; a word
  whose analysis scrolled away can always be looked up again.
- **Deeper analysis** — on a finished answer, a control that asks the
  same word again from the paid model with a fuller brief: every sense
  the word has rather than the card-worthy few, a real etymology, more
  usage and register detail, more examples. **It never touches the
  card** — the note already added stands exactly as it was, and the
  deeper text lives in the app only, appended to the answer rather than
  replacing it. That is the whole point of the split: the deck stays
  compact and reviewable while the app can go as deep as the reader
  wants. Asking twice for the same word costs nothing — the text is kept
  with the history entry and shown again. When no paid model is
  configured or the daily cap is spent, the control says so instead of
  quietly answering from the pool: the user asked for the better model.
- **Rebuild the card** — on any entry in the history, ask the paid model
  to build the note again: for a weak or plainly wrong card, and for the
  case the context was only understood afterwards. It uses the entry's
  context when there is one, replaces the note that entry produced, and
  keeps the audio, which belongs to the word rather than to the answer.
  Unlike the deeper analysis, this one *is* about the deck — it is the
  only control that rewrites a card, and it never fires on its own.
  Bounded by the same daily cap, and refused with a reason when the cap
  is spent or no paid model is configured.
- **Status view** — backend health, AnkiWeb sync state (last result,
  whether unsynced changes are waiting).
- **Stats view** — how many words were added today, over the last
  7 days, and in total, broken down by source language; these are
  counted from the Anki collection itself, so they are accurate
  regardless of restarts. Duplicate and lookup-only sends create no
  card and are therefore counted in memory, labeled as being since the
  last restart.
- **Undo** — remove the note created by the last submitted word of the
  currently selected language (mistaken sends). When the last word
  created nothing — it was a duplicate or a lookup-only request — undo
  reports that there is nothing to undo and changes nothing: it must
  never delete a note that existed before the last send.
Undo acts on the most recent word **per source language** and only since
the backend started — acceptable for a personal tool. There is no plain
"run it again" control: re-rolling the same model on the same prompt is
not how a weak answer gets fixed. Rebuilding the card is, and it acts on
the entry the user is looking at rather than on whichever word happened
to be last.

## Non-functional requirements

- **Latency**: **complete answer within ~20–30 s** — the one budget, and
  the only one worth stating; card added within ~5 s after generation
  ends. Audio is fetched concurrently and must not extend these budgets.
  Time to the first token is deliberately not a requirement: it measures
  how quickly a model starts talking, not how long the user waits, and
  bounding it would prefer a model that trickles for a minute over one
  that thinks briefly and then answers at once.
- **Cost**: **no metered API is ever required.** Every answer starts on
  the free-tier `llmbroker` model pool, which is un-metered. A paid
  per-token model is reached in exactly two situations, both bounded by a
  daily cap (`ECHOWORDS_API_DAILY_CAP`): when the pool fails to start an
  answer within the latency budget, and when the user explicitly asks for
  a deeper analysis. With no paid key configured, or with the cap spent,
  both simply do not happen — the pool timing out then reports a failure
  instead, and the deeper analysis says it is unavailable. The design
  must run fully on the un-metered pool.
- **Safety**: both LLM backends are plain text→text API calls — no
  shell, no filesystem, and no arbitrary network reach — so a prompt
  hijacked by malicious input has nothing to exfiltrate with: the
  indirect-prompt-injection risk that shaped earlier designs is
  structurally absent. The one place untrusted LLM output meets the
  user is rendering: the answer's HTML is reduced to the whitelisted
  `<b>`/`<i>` tags before it reaches the page, and a `suggestion` must
  pass the same validation as typed input before its button is offered.
  The app itself is reachable only inside the tailnet — no public
  attack surface.
- **Resilience**: the backend host is always-on but can still fail (a
  free-tier instance may be reclaimed). When it is unreachable the app
  cannot answer — accepted: the product's value is the immediate
  explanation, and an answer hours later is worth little. Words
  submitted while unreachable are kept in the app's local queue and
  re-sent automatically, in order, on the next successful open — so
  they still become cards. The collection is a local file: cards added
  while AnkiWeb sync was failing survive restarts and reach the devices
  on the next successful sync. Nothing else on the backend is durable
  by design — a restart empties the history and the in-memory
  counters, which is acceptable precisely because every word that
  mattered is already a card.
- **Single instance, single user.** Tailnet membership is the only
  access control; the design assumes the owner is the only user. No
  horizontal scaling concerns.
- **Languages**: multiple **source** languages (each its own deck), a
  single **target** language for all explanations and translations
  (Russian by default), both set in configuration. Adding a language is
  a config change (a languages-table entry), not a code change. The
  target-language setting exists app-wide, but v0.1's UI strings and
  prompt scaffolding are Russian — changing the target language changes
  the answer language, not the interface language.
- **Accent**: applies to English audio (dictionary recording choice and
  TTS voice), set per language in configuration; American by default.
  Never two recordings per card.

## Out of scope — final

These are decisions, not deferrals: chat-platform interfaces (the
Telegram bot included — see `decision-interface.md`), native mobile
apps, public internet exposure (the app lives inside the tailnet),
multiple **users** (multiple **source languages** with separate decks
for the single user ARE supported), example-sentence audio, Docker.
