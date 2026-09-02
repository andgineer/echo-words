# echo-words — Functional Description

The source of truth for *what* to build. Together with the
`decision-*.md` records it is the complete specification for the
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
   each language needs is settled by experiment
   (`spec/decision-llm-backend.md`), not by assumption.
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
  reached on latency — the pool did not finish the answer inside its
  attempt budget — and on the two things the user asks the better model
  for by name: a deeper analysis, and rebuilding a card. The free pool is un-metered
  and the paid step is capped and optional, so **no metered API is ever
  required**. How good each step is per language was settled by a
  benchmark that ran *before* the build (`spec/decision-llm-backend.md`).
- **Anki** — a server-side Anki collection maintained by the backend
  itself through the headless Anki Python library (pylib) — no Anki
  application and no AnkiConnect run next to the backend. The backend
  adds notes to its own collection in-process and synchronizes it with
  **AnkiWeb**; the user reviews in AnkiDroid / AnkiMobile / Anki
  desktop exactly as before, syncing from AnkiWeb. (Decision record:
  `decision-spaced-repetition.md`.)

## Core flow

1. The user picks the source language (the selector remembers the last
   choice) and submits exactly the word, expression, fragment or text they
   want analysed. A lookup-only request — the answer and audio arrive as
   usual but no Anki note is created — is made with the control next to the
   input; prefixing the text with `?` does the same.
   Every compact answer uses one prompt and one hidden discriminated payload.
   A single source word is a known vocabulary unit. For an ordinary
   multi-word submit-box request the model decides, in that same answer,
   whether the input is one lexical `unit` or `text` containing units; no
   punctuation or word-count classifier and no preliminary model call exist.
   The boundary is semantic rather than grammatical and deliberately
   conservative. An ordinary utterance with a freely chosen participant,
   current argument, time, place, degree or other surrounding event detail is
   text even when it contains a reusable lexical unit. A finite clause with a
   particular subject, object, complement, experiencer or subordinate
   proposition remains text even when a fixed expression occupies most of it;
   the expression is offered separately as a combination. Uncertainty between
   a whole-clause unit and text containing a unit resolves to text. The only
   finite-clause exception is a conventional fixed formula whose whole wording
   is reusable as-is; genuinely borderline reusable short formulas may still
   reasonably take either branch.
   Borderline reusable chunks are expected; the backend does not overrule the
   returned branch from article wording or an exact dictionary-boundary check.
   A unit answer shows the full dictionary article. A bare word shows every
   target-language-distinct sense and cards the most common one; a set
   expression explains both its meaning and its components and cards the
   expression itself. A text answer translates and explains the whole text,
   makes no note, and offers every source word as a chip, with a chip for each
   non-overlapping lexical combination alongside them.
   Tapping any chip submits the chip's visible label with explicit unit intent
   and the context stored on that chip. A chip under text carries the complete
   submitted text; a sense chip carries one of that sense's examples exactly
   when it fits the 500-character context bound, and otherwise becomes a bare
   lookup; component chips under a set expression preserve every word-shaped
   part in expression order and carry the first example of the expression's
   carded sense. The model must then return a unit answer. A context unit
   answer leads with the sense used there, keeps the remaining senses below
   it, and cards the named sense (the first retained sense if the index is
   unusable). Every sense, including the one just carded, remains available as
   a chip.
   The raw submission remains the history entry and the PWA audio target. The
   validated dictionary headword returned by a unit answer is the identity
   used by the note and its Anki audio. This is what lets an inflected or
   separated chip such as `gave up` become a note for `give up` without
   rewriting what the user submitted. Spelling correction remains a separate,
   advisory control.

2. The backend validates the input against the selected language's
   allowed script (Latin with accented letters — café, naïve, Straße —
   for English and German; Latin or Cyrillic for Serbian) and length
   within a small limit. Punctuation clinging to the edges of a unit is
   dropped before it is judged, because a shared selection carries it:
   “Straße.” is the word Straße. Running text is held to the same
   script rule word by word — so it keeps its commas, digits and
   quotation marks — and to a longer 500-character length bound, the same one
   that caps the context a suggested unit is submitted with. Anything else —
   including a language code not present in the configuration — gets a
   short hint instead of an LLM call. The language is always the user's
   explicit selection, never guessed from the word (auto-detecting the
   language of a single word is not reliable enough to trust with deck
   placement).
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
   absorb. An answer that arrives in time but carries no usable hidden
   payload — an unusable unit or text branch, including a text verdict for an
   explicit unit-intent request —
   is not complete either, and moves the request the same way: a free
   model that writes a good analysis and then botches the payload costs
   the user the requested result, which is the point of the request. The pool call is
   rated down before the paid model is asked, so the router learns which
   model does this. When the move happens mid-answer, or after a whole
   answer that turned out unusable, the text already shown is discarded
   and replaced by the paid model's. Which model answered is
   visible on the entry; nothing else about the two paths differs, and
   the card is built from whichever answer arrived.
   The step-up happens at most once per request: when no paid model is
   configured or the daily cap is spent, an unusable answer stands as it
   is — the analysis is worth reading even when the card behind it failed,
   and the entry says the card failed. Every rejected payload is logged
   with the reason it was rejected and the payload itself, since nothing
   else keeps it.
   The step-up is failure recovery, not part of the normal latency path.
   The paid model starts a new attempt with the same full complete-answer
   budget as the pool; time already lost waiting for the failed pool does
   not make the paid model capable of answering faster. A recovered request
   may therefore take two complete-answer windows end to end. This is the
   explicit emergency exception to the normal latency target, not a shared
   deadline split between the two models.
   **How fast the first token arrives is not a criterion and is never
   measured.** It is the easiest number in the system to look good on and
   the least related to what the user waits for: a model that emits one
   token immediately and the rest over a minute has answered slowly. Only
   the complete answer is judged, and streaming is a display choice —
   text appears as it is produced rather than in one jump — not a
   deadline of its own.
5. Words are processed one at a time, in the order submitted — never as
   parallel LLM runs.
6. The LLM produces both outputs in one generation: the full visible
   article and one hidden `unit` or `text` payload. The payload is never
   shown. A unit payload contains the validated dictionary headword, its
   claimed relation to the submitted spelling (`same`, `morphology` or
   `typo`), the advisory spelling suggestion, every target-language-distinct
   sense, a marked-up form for every example, the contextual sense when
   applicable, and expression components. The plain sentence and the blanked
   form are both derived from the marked-up one, so an example carries its
   sentence once and the three forms cannot disagree. A text payload contains
   only proposed multi-word lexical combinations. Each proposal keeps a distinct
   unit separate and copies every lexical surface piece token for token from the
   submitted text in its original script and capitalization. The backend builds
   the visible chip list from those proposals **and** every submitted source
   word, so a word which a combination also claims still gets its own chip.
   A complete response is
   limited to 16,000 characters before JSON decoding or chip filling. No
   attempt exposes more than that prefix; excess output is drained so the pool
   call settles and can be rated down. An oversized free-pool answer is unusable
   and takes the ordinary paid fallback, while an oversized final attempt cannot
   create a note from a valid-looking truncated prefix.
7. In parallel with the LLM call, the backend obtains audio for exactly the
   submitted text. Once a unit answer supplies its dictionary headword, that
   audio is reused for Anki only when the NFC-normalized strings are exactly
   equal, including case; otherwise the backend separately obtains audio for
   the carded headword. Context audio is a third, independent path where a chip
   carries surrounding text. After generation, every outstanding role is
   resolved concurrently under one shared hard maximum of ten seconds; a
   timeout or failure yields the corresponding missing-audio status and cannot
   hold storage or completion for the old per-role timeout.
8. When generation completes, the entry gains its submitted-text
   pronunciation. A usable unit answer creates one note unless the request is
   lookup-only; a text answer creates none. Every accepted note generates all
   four templates, and the status line names their four distinct localized
   kinds. The collection lives in-process, so adding a note cannot fail because
   Anki is not running; delivery to other devices happens through the debounced
   AnkiWeb sync.

Finished and in-progress entries live in a server-side history (see
"UI actions"), so closing the app mid-generation, an interrupted event
stream, or opening the page on another device never loses an answer
while the backend is up.

## Analysis content (the answer)

The answer contains, in this order:

- **Translations into the target language** (Russian by default; the
  target language is an app-wide configuration setting), ordered by
  likelihood in everyday speech, and nothing in front of them: the
  answer opens on the meaning, because that is what was asked for. A
  register mark (neutral / colloquial / formal / slang) follows the
  translation it belongs to, where it matters. The part of speech is
  never named — it costs a line at the top and tells the reader what
  they already knew.
- **Forms**, when and only when the word changes shape in a way the
  reader has to recognise or produce. A compact table whose cells are
  short everyday phrases with their translations: the phrases carry the
  grammar, so no person, number, gender, case or tense is ever named.
  An invariable word gets no table at all — the section is a signal, not
  a fixture.
- **Usage notes**: typical collocations and prepositions, common
  confusions with similar words, countability when relevant.
- **Origin**: if the word was borrowed into the source language from
  another language, a short story of where it came from and how it
  traveled; otherwise a one-line note on origin. No forced etymology
  essays for native words.
- **Examples**: 2–4 short sentences from everyday contexts, each with a
  Russian translation.

Additional behavior:

- If the input looks misspelled, the card is made for the corrected wording and
  the entry says so above the analysis — or no card at all, when the answer would
  not correct the spelling it calls wrong; if the wording is not used at all, no
  card and no article are made. See "Spelling: the card carries the word that
  was analysed".
- For idioms and phrasal verbs: the meaning, literal vs figurative sense,
  and typical situations where it is used.
- The answer stays compact (~3,500 characters at most) — it is a
  lookup, not an essay.

**A running-text answer** is a different shape: the text rendered whole
in the target language, then a short list of what is hard *in this
particular text* — a construction, the word order, a case or a mood, a
set expression, a word that is not what it looks like. It is never a
word-by-word walk-through. Its hidden payload proposes every clear
multi-word unit worth learning whole, with no numerical cap and an empty list
when none qualifies. The backend maps each usable proposal to the source
occurrences, displays those exact inflected forms in source order, ignores an
unmatchable proposal, resolves overlap in favour of the first proposal, and
adds every source word as its own chip whether or not a combination claims it.
Repeated occurrences stay separate.

## Spelling: the card carries the word that was analysed

Two different failures live here, and they need different answers. A **misspelling**
means a real word was meant and written wrong. A **coinage** means no word was meant
at all — a string that is merely well formed, which a model asked for a dictionary
article will invent one for, complete with origin and usage examples. Measured on the
free pool, an article prompt refuses none of six such strings; the paid models refuse
none either. Intelligence is not the lever here, the question is.

**A unit submission is judged twice, and either judgement can withhold it.** The
answer opens with a verdict on the submitted wording — used or not, and where it is
used — before it writes anything else; alongside it, a second pool call asks that
question and nothing else. A refusal from either means no article, no card and no
audio, and the entry says the wording is not vouched for. Rarity is never a reason to
refuse; wording real speakers use in any register, field, dialect or period is used,
however uncommon.

**A refusal is a judgement about one lexical unit, so it cannot withhold running
text.** The standalone question is asked only where the submission is one unit, and
a verdict at the head of an answer to a multi-word submission says the answer took
the unit branch when it should have taken the text one. Such a submission is read as
text instead of refused: no card, nothing the answer wrote about wording it had just
refused, and a chip for each submitted word — a row the backend builds from the
submission itself. Losing the whole submission to a question that was never about it
would cost the reader more than the mis-branched answer did.

**The question is asked apart because the framing is what decides the answer.** The
same instruction, on the same free pool and the same fixtures: prose inside the
article rules withheld none of six coinages, a verdict at the head of the article
call withholds two, and the standalone question withholds three to six over six
samples. A model already writing a dictionary entry has an entry to produce; asked on
its own it has nothing to produce but the judgement. Rare real wording survived every
run of all three. What the standalone call reaches are the well-formed compounds
nobody says — `Fahrradsuppe`, `Löffelangst` — which the article's own verdict never
withheld and this one refuses in most runs, though not in all of them.

Nothing is shown until the wording has been vouched for: the article is held while it
streams and released only once the judgement lands, because streaming a fabrication
and blanking it afterwards is the reader having seen it. The judgement is one line and
normally arrives first, and the two calls run together, so the reader waits for the
slower of the two rather than for their sum. An answer that omits the verdict, or a
judgement that never arrives, is treated as no objection: closing on the model's
silence would refuse real words, which is the worse error.

**A judgement about the submitted wording is overruled by an answer about another
one.** The standalone question refuses four of six registered misspellings — being
unused is what a misspelling is — so taking it at face value would answer every typo
with "no such word" instead of the correction. It withholds only over an answer that
stayed on the wording it judged. What that leaves uncovered is a misspelling no
answer corrected: the entry then says the wording is not vouched for, which is the
right thing to say about it and not the correction the reader wanted.

**A note is stored only for the wording its answer analysed.** Where the answer
analysed another spelling, the card is for that word — applied, not offered, because
a note pairing the learner's spelling with another word's meanings, examples and gap
teaches a word no sentence on it contains. Nothing is silent about it: whenever the
entry is about wording other than what was submitted, it says so above the analysis,
for a lookup and a failed card as much as for a stored one, and undo removes what was
stored. Only a misspelling the answer declares is *named* as one — a dictionary lemma
for an inflected form is the ordinary case, and calling it a typo would accuse the
learner on a large share of everything they submit. The parser keeps the analysed
headword and drops a suggestion that merely repeats it.

**An answer that calls the submission misspelled and still heads itself with that
spelling cards nothing.** Its only card would teach the spelling the same answer
calls wrong. The article stands, the entry says the wording looks misspelled, and
the correction stays one tap away. The prompt asks for the lemma in the heading, but
nothing verifies the visible heading against the stored wording: the card is bound to
the parsed answer, not to the prose.

Where the answer analysed the submitted wording and still names another spelling, the
card is the learner's and the entry offers to replace it with the other one.

**A declared misspelling is handed to the paid model, and a refusal is not.** The
paid models are measurably better at exactly one thing here: six of six registered
misspellings corrected against the pool's four. They withhold no coinages at all, so
a refusal sent up for review would be overturned by the weaker judge of the two, and
it stays with the pool. Ordinary wording never reaches the paid model. The cost is
therefore one paid call per suspected misspelling, inside the daily cap, and none for
the vast majority of submissions. Stepping up on this policy is not a complaint about
the answer, so the pool model that produced it keeps its rating.

**A card sentence must be written in the language being learned.** An example whose
sentence is in the target language with the source word wedged into it — "Мы должны
receive письмо" — is a card front that teaches nothing, and answers produce them. The
prompt asks for the sentence to be written entirely in the source language and in one
script from end to end.

Behind that, the sentence outside the highlight is tested for letters the source
language does not have, and an example failing it is dropped; an entry left with no
usable example is unusable and steps up. That test is a filter and not a proof, and
for Serbian it is the weakest: Serbian shares its Cyrillic with Russian, so only the
nine letters Russian has and Serbian does not can separate them, and a Russian
sentence using none of the nine passes — "Он живет в великом граду на берегу реки"
shipped as a Serbian card front. Writing the sentence in the right language is the
answer's job; no deterministic test can finish it, and widening this one is not the
way to try.

**None of this proves linguistic intent, and the operating point is accepted rather
than solved.** A model can still call a coinage attested: none to three of six survive
both judgements, one of them carded with an invented register and an invented
etymology on the most recent tier, and what survives is the well-formed compound — `Fahrradsuppe`,
`bookshelfy`, `tablewards` — carded with an invented sense, an invented register and
an invented origin. That is the known cost of shipping without an attestation source,
and no free source covers English, German and Serbian alike. Registered fixtures of
both classes — real rare wording and well-formed nonsense — plus fresh semantic review
of the concrete answers stay part of every prompt promotion gate, because the number
moves with the prompt and cannot be read off the code.

Behavior is fixed, not configurable:

- The raw submission remains visible in history and is voiced as submitted —
  except wording the answer would not vouch for, where no recording is offered.
  Speech is fetched while the answer streams, so the file may already exist and
  stay in the cache; what the refusal withholds is the player, not the bytes.
- A valid suggestion is held to the same language and input rules as typed unit
  text, and lookup-only stays lookup-only.
- A switch replaces the note and card audio it had, and a switch that stores
  nothing leaves the previous note and its media exactly as they were, and says so.
- The controls act on their own in-memory history entry and expire on restart.

## Pronunciation audio

Audio is a core feature, not an add-on: every word gets pronunciation
both in the answer entry and on the flashcard.

- **Scope**: everything the user submits is voiced — a word, a phrase and
  a running text alike. Example sentences inside an answer are never
  voiced — a final decision, not a deferral: cards must stay light and
  generation fast.
- **The app never voices less than what was submitted.** A note can only
  carry the audio of what is on it, so when the card holds a unit taken
  out of a longer text, the entry offers the unit's pronunciation *and*,
  beside it, the whole text that unit came from. Running text, which
  makes no note at all, is still voiced whole in the app.
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
    one tap to hear, replayable from the history. Where the whole text
    is voiced beside a unit, it is a second player of its own, and only
    the unit's pronunciation starts by itself.
  - Anki: the audio of the carded unit is attached to the card front, so
    it plays during review. The audio of a surrounding text never is.
- **Resilience**: submitted-text audio starts in parallel with the LLM call
  and must never fail the answer. After parsing, it is reused for the note only
  when the validated dictionary headword is the same NFC-normalized,
  case-sensitive text; otherwise card audio starts separately. Submitted,
  context and newly known headword audio share one concurrent post-generation
  wait capped at ten seconds. Rebuild reuses card audio only while the returned
  headword is exactly unchanged, and correction always fetches for the newly
  selected spelling. A slow or failed role is cancelled independently, the note
  and answer go out without that audio, and the status distinguishes missing
  submitted-text audio in the PWA from missing headword audio on the Anki card.

## Anki cards

- **Running text never produces a note.** A sentence or clause is not one
  stable vocabulary stimulus. Its all-word and combination chips are the path
  from reading to a unit note.
- **One submission creates at most one note, about one sense.** A bare word
  cards its most common retained sense; explicit unit intent with context cards
  the retained sense the answer names as the one used there, falling back to
  the first.
  Senses mean distinctions that need different target-language words, not every
  subdivision a monolingual dictionary might list. The same word may be
  submitted again and creates another note; there is no deduplication.
- **Every accepted note generates exactly four cards:**
  1. word, optional short sense label and audio → translations;
  2. translations and optional short sense label → word and audio;
  3. the complete sentence with every surface part of the unit highlighted →
     translations, word and audio;
  4. translations plus the complete sentence with every surface part replaced
     by `___` → word and audio.
  The label appears on the two bare fronts only when the unit answer retains
  several cardable senses. Cardability is established before that requirement,
  so a malformed sibling cannot make an otherwise valid singleton with an empty
  label disappear. The sentence itself disambiguates the two contextual fronts.
- The sentence is the supplied context for a chip/card request and otherwise
  the first example of the carded sense. For supplied context, the backend maps
  the exact submitted click surface into that exact context in source order and
  constructs both fronts when every selected token can be found. This prevents
  the model from expanding a selected word or combination to its subject,
  object or surrounding clause. Otherwise the model returns the highlighted form
  alone. The backend accepts it only when it is exactly the plain example with
  one or more bold spans added and at least one source-language word remains
  outside the unit, and then builds the gapped form by replacing those spans
  with blanks. It does not infer
  morphology or decide which words linguistically belong to a generated unit.
  For an example generated without supplied context, there is one narrower
  structural check: any submitted-unit token which also occurs in the returned
  headword and literally occurs in the example must occur in the highlighted
  target. This catches an unmarked unchanged component without assuming that a
  differing token is an inflection of the unit.
- The visible article remains the full dictionary explanation with all retained
  senses, forms where useful, usage, origin and examples. The six Anki fields
  contain only the selected sense's word, audio, optional label, translations,
  highlighted sentence and gapped sentence.
- The status line reports all four distinct template kinds. Undo removes the
  note with all four cards.

- **One deck per source language**, set in the languages configuration
  (e.g. `EchoWords: English`, `EchoWords: German`,
  `EchoWords: Serbian`). The language selected at submission determines
  the deck — there is no per-word deck switching, and the deck is never
  guessed from the word itself.
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

- **About/help note** — what the app does, the two input shapes, the
  lookup-only control and `?` shortcut, and the ✏️ correction button for
  a suspected typo.
- **Chips** — under a text answer, every source word plus one chip for each
  accepted combination, each combination standing before its first word; under a set
  expression, its component words; under a single word or any explicit card
  request, every retained sense. Each chip submits its own stored context and
  explicit unit intent rather than making the frontend reconstruct either.
- **History** — the answer area shows recent words with their finished
  analyses, pronunciation, and status; in-progress entries appear with
  their text accumulated so far. History is served by the backend, so
  it survives reloads, a dropped connection mid-generation, and
  switching devices — but it is held **in memory only** and starts
  empty after a restart. The cards it produced are unaffected; a word
  whose analysis scrolled away can always be looked up again.
- **Deeper analysis** — on a finished word answer, a control that asks the
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
  It does not apply to running text, which has no single word to go
  deeper on.
- **Rebuild the card** — on a unit entry that successfully added a note,
  ask the paid model to build the note again: for a weak or plainly wrong card, and for the
  case the context was only understood afterwards. It uses the entry's
  context when there is one, reuses the stored unit headword and explicit unit
  intent, and replaces the note that entry produced. It reuses card audio only
  when the rebuilt answer returns the same headword.
  Unlike the deeper analysis, this one *is* about the deck — it is the
  only control that rewrites a card, and it never fires on its own.
  Bounded by the same daily cap, and refused with a reason when the cap
  is spent or no paid model is configured. It does not apply to running
  text, which produced no card to rebuild.
- **Status view** — backend health, AnkiWeb sync state (last result,
  whether unsynced changes are waiting).
- **Version in the header** — the version of the build the page is
  running, beside the app name. It comes from the package version baked
  into the bundle at build time, so a page still served from the PWA
  cache after a deploy can be told apart from the freshly deployed one.
- **Stats view** — how many words were added today, over the last
  7 days, and in total, broken down by source language; these are
  counted from the Anki collection itself, so they are accurate
  regardless of restarts. Lookup-only sends create no card and are
  therefore counted in memory, labeled as being since the last restart.
- **Undo** — remove the note created by the last submitted word of the
  currently selected language (mistaken sends). When the last word
  created nothing — a lookup-only request, a running text, or a card that
  failed — undo reports that there is nothing to undo and changes
  nothing: it must never delete a note that existed before the last
  send.
Undo acts on the most recent word **per source language** and only since
the backend started — acceptable for a personal tool. There is no plain
"run it again" control: re-rolling the same model on the same prompt is
not how a weak answer gets fixed. Rebuilding the card is, and it acts on
the entry the user is looking at rather than on whichever word happened
to be last.

## Non-functional requirements

- **Latency**: on the normal path, **complete answer within ~20–30 s**.
  This is the complete-answer budget of one model attempt, and the only
  latency number worth stating. The emergency pool → paid recovery gives
  the paid attempt a fresh budget of the same size, so a recovered request
  may take ~40–60 s end to end; requiring the paid model to consume only
  whatever time the failed pool left behind would not make it answer faster.
  The card is added within ~5 s after generation ends. Outstanding audio roles
  are waited concurrently under that same hard maximum and cannot extend it.
  Time to the first token is deliberately not a requirement: it measures
  how quickly a model starts talking, not how long the user waits, and
  bounding it would prefer a model that trickles for a minute over one
  that thinks briefly and then answers at once.
- **Cost**: **no metered API is ever required.** Every answer starts on
  the free-tier `llmbroker` model pool, which is un-metered. A paid
  per-token model is reached in exactly two situations, both bounded by a
  daily cap (`ECHOWORDS_API_DAILY_CAP`): when the pool fails to deliver a
  complete and usable answer within its attempt budget, and when the user
  explicitly asks for a deeper analysis. With no paid key configured, or with the cap spent,
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
  **interface language** is a separate, per-device choice between English
  and Russian, offered in the app's header and defaulting to English. It
  covers the app's own strings and the input hints the backend returns to
  that request, and it never changes the target language. Prompt
  scaffolding and everything the backend streams into the shared history —
  card statuses and the analysis itself — follow the target language,
  because that history is broadcast to every client at once.
- **Accent**: applies to English audio (dictionary recording choice and
  TTS voice), set per language in configuration; American by default.
  Never two recordings per card.

## Out of scope — final

These are decisions, not deferrals: chat-platform interfaces (the
Telegram bot included — see `decision-interface.md`), native mobile
apps, public internet exposure (the app lives inside the tailnet),
multiple **users** (multiple **source languages** with separate decks
for the single user ARE supported), example-sentence audio, Docker.
