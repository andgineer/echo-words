# Spaced repetition without a running Anki GUI — research & decision

Status: **researched 2026-07-17 — recommendation: replace AnkiConnect
with the headless Anki Python library (pylib) syncing to AnkiWeb; the
user keeps reviewing in AnkiDroid/AnkiMobile/desktop unchanged.**
Adopting the recommendation amends the functional description and the
implementation plan (M5, M7) — see "Impact on the plan" at the end;
those edits are deliberately NOT applied by this document.

## The problem with the current plan

The plan integrates with Anki through **AnkiConnect**, which is an
add-on inside Anki desktop: it only works while a full Qt GUI
application is running. That anchors the backend to the laptop, makes
the deployment heavy (a desktop app as a service dependency), and rules
out running wordgram as a small headless service on Oracle Cloud Free
Tier. The research question: is there an architecture that

- needs no always-running GUI application,
- keeps the backend small (code, RAM, CPU),
- minimizes our own code,
- can run permanently on Oracle Cloud Free Tier,
- and does not degrade the user experience vs the current plan
  (cards appear automatically, reviews happen in a polished mobile app,
  audio plays on the card).

## Option A — GetSpace ("Space", getspace.app): rejected

Space is a modern Anki alternative (FSRS-6, native apps on iOS /
Android / macOS / Windows / Linux, free core tier, cloud sync).
Verified against getspace.app and its CLI docs, 2026-07-17:

- **No server / REST API.** Nothing an external service could call to
  create cards.
- **`space-cli` is not a server path.** The CLI can create/edit/export
  cards, but it explicitly requires the Space **desktop app installed
  on the same machine** — it reads the app's local database, and sync
  to other devices happens "next time the Space app is online". That
  is architecturally the same anchor as AnkiConnect (a desktop app as
  the integration point), only proprietary and closed-source on top.
- Media/audio attachment via the CLI is undocumented; audio on the
  card is a hard requirement for us.

Verdict: Space cannot replace Anki even partially in a server
architecture. The very problem we are solving (integration requires a
local desktop app) is the way Space is built, by design ("local-first").

## Option B — headless Anki: the `anki` Python library (pylib): **recommended**

Anki's own non-GUI core ships as a standalone PyPI package `anki`
(pylib over a Rust backend). Verified 2026-07-17:

- **Runs headless.** No Qt, no display. Precedent: `apy`
  (github.com/lervag/apy) manipulates collections with pylib alone,
  no Anki installation, no running app.
- **Full programmatic surface** — everything M5 needs from
  AnkiConnect exists as direct in-process calls on
  `anki.collection.Collection`: create decks and note types, add/find/
  delete notes, add media files, and **sync**:
  `sync_login(username, password, endpoint) -> SyncAuth`,
  `sync_collection(auth, sync_media)`, `sync_media(auth)`,
  `sync_status(auth)` (signatures confirmed against ankitects/anki
  main).
- **Fits Oracle Free Tier.** Version 26.5 publishes
  `manylinux_2_35_aarch64` wheels — it runs on the Always Free ARM
  (A1.Flex, up to 4 OCPU / 24 GB) as well as x86. The process is one
  Python service with an embedded Rust core — tens to a couple hundred
  MB of RAM, no GPU, no display server.
- **UX is fully preserved — this is the decisive property.** The
  backend maintains its own collection server-side and syncs it to
  **AnkiWeb**; the user's AnkiDroid / AnkiMobile / desktop sync from
  AnkiWeb exactly as in the current plan (the plan already relies on
  AnkiWeb sync — M5's debounced `sync`). Reviews stay in the Anki apps
  the user already knows: offline, FSRS scheduling, statistics, audio
  on the card. Nothing the user touches changes at all; only the
  invisible integration side changes.

What changes in the backend, compared to AnkiConnect:

- `anki.py` becomes a pylib wrapper instead of an httpx client — the
  same operations, in-process, no localhost HTTP hop. Model/deck
  bootstrap, deck-scoped dedup, `[sound:...]` media, two card
  templates: all map 1:1.
- **The pending queue shrinks to a sync-retry.** "Anki is not
  running" ceases to exist as a state — the collection is always
  available in-process, so `addNote` can no longer fail with a
  connection error. Only the AnkiWeb sync can fail transiently, and
  it is already debounced and non-blocking in the plan. M7's
  `pending_notes` machinery (queue, drain task, queued-vs-added
  statuses) collapses; `word_log`, `/undo`, `/redo` survive unchanged
  but simpler (a note is always either in the collection or not).

Risks, honestly:

1. **Sync auth from a script.** Anki 24.11+ tightened what add-ons may
   pass to `sync_login`, but the pylib call itself remains public
   (signature above), and the Anki forum documents a supported
   headless path: obtain `SyncAuth`/hkey once via `sync_login`, store
   it, reuse it for `sync_collection`/`sync_media`. This needs a
   half-day spike (like M0) before amending M5 — log in, add a note
   with audio server-side, watch it arrive on AnkiDroid.
2. **pylib API churn.** pylib is versioned with the app and refactors
   between releases. Mitigation: pin `anki==` in `uv.lock` (already
   the project norm) and upgrade deliberately. `apy` has tracked this
   for years with modest effort.
3. **One writer.** The server collection is written only by wordgram
   and only synced elsewhere — no concurrent-writer problem by
   construction (single-instance NFR).
4. **AnkiWeb dependency.** If the auth path ever breaks, the fallback
   is Anki's **official self-hosted sync server** (built into the same
   package, a tiny process, docs.ankiweb.net/sync-server) on the same
   OCI instance; AnkiDroid and AnkiMobile both support a custom sync
   endpoint. Same architecture, one extra small always-on process, no
   AnkiWeb. Not the default because AnkiWeb costs zero ops and the
   user already has the account.

## Option C — own spaced repetition in the bot (Glosbe-style): viable, kept as the strategic alternative

The "don't integrate, implement" path the research asked to price out.
The scheduling itself is a solved problem — **`py-fsrs`**
(open-spaced-repetition/py-fsrs, the reference Python FSRS
implementation, `pip install fsrs`) gives the same modern algorithm
Anki itself now uses: `Scheduler.review_card(card, rating)` with
Again/Hard/Good/Easy, card state serialization to dict — a natural fit
for one SQLite table next to the ones M7 already creates. Reviews
happen **in the same Telegram topics**: the bot sends the card front
(word + voice message — Telegram lets a cached `file_id` be re-sent for
free), a "show answer" button, then four grading buttons; a daily
message says how many cards are due per language. Inline keyboards are
exactly the primitive `decision-chat-interface.md` already praises for
"in-chat spaced repetition", and a Telegram Mini App remains the
richer-UI escape hatch (a separate PWA would violate the "no web UI —
final" scope decision, so it is not proposed).

Cost/benefit vs Option B:

- **Pro:** the entire Anki surface disappears — no pylib, no AnkiWeb,
  no note types, no sync, no external anything. The backend becomes
  the whole product: one process, SQLite, py-fsrs (~pure-Python,
  trivial footprint). This is the true minimum for RAM/CPU/moving
  parts, and every future feature (custom exercises, LLM-generated
  quizzes) is easier because we own the review loop.
- **Con — the UX regression the goals forbid:** reviewing in a chat
  is linear and online-only; Anki apps give offline review, swipe
  flow, per-deck stats, and the user's existing habit and history.
  Review-in-chat is a *different* product experience, not a drop-in
  replacement. It also adds the most *new* code of all options
  (review session flow, due-card querying, grading handlers, stats —
  a few hundred lines plus tests), whereas B mostly *deletes* code
  (the queue) — "minimize own code" favors B, not C, once a review UI
  is included.

Verdict: not for v0.1. Adopt only if the owner decides chat-based
review is *desirable in itself* (always-with-you reviews in the same
place words are added); it is a product pivot, not an integration
swap. B does not block it later: FSRS state can be built from scratch
or imported, and the bot already owns card content.

## Option D — Mochi (SaaS with a real REST API): rejected

mochi.cards has what Anki lacks: a documented REST API (HTTP basic
auth with an API key) with `POST /cards`, deck management, and
`POST /cards/:id/attachments` for media (mp3 works) — the backend
would be a thin HTTP client, thinner than any other option. Rejected
anyway: API access requires the **paid Pro subscription** (the project
NFR is "no metered API cost", and this adds a permanent subscription
for a personal tool), the scheduler is proprietary (not FSRS),
review history would live in a closed SaaS, and the concurrency limit
(one request at a time) — while fine for our volume — underlines that
the API is a side feature, not a platform. A reasonable plan-B SaaS if
self-hosting ever becomes unwanted.

## Option E — `genanki` + .apkg delivery: rejected

Generate an `.apkg` server-side (genanki, pure Python) and send it in
the chat; tapping it on the phone imports into AnkiDroid. Zero server
state, but every batch needs a manual import tap, `/undo`/`/redo` and
dedup degrade to hope, and sync conflicts between generated packages
and the live collection are the user's problem. Fails "no UX
regression". (Running full Anki desktop + AnkiConnect headless under
Xvfb in Docker — the community workaround — is rejected without
discussion: it is the current plan's flaw made heavier.)

## Effect on pronunciation audio

Leaving AnkiConnect does **not** disturb the audio pipeline — M6's
chain (dictionary recording → local Kokoro/Piper → edge-tts) is
independent of the card store:

- **Option B:** the mp3 goes into the server collection's media via
  pylib (`media.add_file` replacing AnkiConnect `storeMediaFile`) and
  the same `[sound:...]` field; `sync_collection(auth,
  sync_media=True)` carries it to AnkiWeb and on to the phone. Card
  audio behaves exactly as in the current plan.
- **Option C (if ever adopted):** audio is delivered as the Telegram
  voice message the bot already sends, re-used at review time via the
  cached `file_id` — no new storage or serving.
- **Platform-built-in voicing** (the "use the platform's own TTS"
  idea) exists in none of the candidates — Anki, Space, and Mochi all
  expect audio to be attached, not generated — so generating at card
  creation stays the design regardless of option. That is the right
  place anyway: generate once, play forever offline.
- **Serbian specifically** needs no compromise and no Croatian
  substitute: Piper has a Serbian voice (`sr_RS`, `serbski_institut`,
  medium — confirm quality at M6 as already planned) and edge-tts has
  `sr-RS-NicholasNeural` / `sr-RS-SophieNeural` (community reports of
  intermittent breakage on the Nicholas voice reinforce edge-tts's
  last-resort-only role). Croatian (`hr-HR`) / Bosnian (`bs-BA`)
  voices remain a documented emergency fallback — phonetically close,
  but a wrong-language recording on a language-learning card is a
  quality cut to take only when everything else fails.
- **On the server:** kokoro-onnx and piper run on CPU via onnxruntime,
  which supports linux aarch64 — the M6 plan works on the Free Tier
  ARM instance. (If the instance is the 1 GB x86 micro instead,
  skipping Kokoro and using Piper + edge-tts is the pragmatic
  configuration.)

## Fit against the research goals

| Goal | A: Space | B: pylib headless | C: own FSRS | D: Mochi | E: genanki |
|---|---|---|---|---|---|
| No GUI app required | ✗ (CLI needs the app) | ✓ | ✓ | ✓ | ✓ |
| Backend stays small | — | ✓ (~one wheel) | ✓✓ (smallest) | ✓✓ | ✓ |
| Minimal own code | — | ✓ (deletes the queue) | ✗ (adds review UI) | ✓ | ✗ (dedup/undo pain) |
| RAM/CPU on Free Tier | — | ✓ (aarch64 wheel) | ✓✓ | ✓✓ | ✓ |
| Runs 24/7 on OCI Free Tier | ✗ | ✓ | ✓ | ✓ | ✓ |
| No UX regression | ✗ | ✓✓ (identical) | ✗ (different product) | ~ (new app, paid) | ✗ (manual imports) |

## Recommendation

**Adopt Option B.** Replace the AnkiConnect client with the `anki`
pylib used headless: the backend owns a server-side collection, adds
notes and media in-process, and syncs to AnkiWeb; the user's devices
are untouched. This removes the GUI anchor (the original complaint),
*reduces* net code (M7's pending queue collapses into the existing
debounced sync retry), keeps every card/audio/review behavior of the
current spec, and runs on Oracle Free Tier ARM today. Gate it with a
half-day spike (auth + add-note-with-audio + AnkiDroid arrival), like
M0 gates the LLM choice. Keep the self-hosted Anki sync server as the
documented fallback if AnkiWeb auth proves fragile, and Option C as
the deliberate product pivot to revisit only if chat-native review
becomes a goal in itself — not as a way to avoid this integration,
which is now cheap.

## Impact on the plan (when adopted)

- **Functional description:** "Backend — a single service on the
  user's laptop, the same machine that runs Anki" becomes "a single
  headless service (laptop or a small cloud instance)"; "Anki desktop
  with AnkiConnect on localhost" becomes "a server-side Anki
  collection (Anki pylib) synced to AnkiWeb"; the "Anki is not
  running" status/queue wording reduces to a sync-pending note.
- **Implementation plan:** M5 rewrites `anki.py` against pylib (same
  tests, mock the collection instead of httpx); M7 drops
  `pending_notes` (keeps `word_log`); config drops `WORDGRAM_ANKI_URL`
  and gains `WORDGRAM_ANKIWEB_USER` / password (or a stored sync key)
  — `WORDGRAM_ANKI_SYNC` semantics survive as-is.
- **Not decided here:** actually moving the backend off the laptop.
  B makes the backend location-independent, but the laptop still
  anchors the **CLI coding-agent** subscriptions
  (`decision-chat-interface.md`'s second anchor); llmbroker is a
  plain API and moves freely. Hosting on OCI (including its known
  idle-reclamation risk, mitigated by Telegram's 24 h buffering)
  is a separate decision to take when v0.1 runs.

References (all checked 2026-07-17): getspace.app + /cli (CLI requires
the installed app; no server API); ankitects/anki
`pylib/anki/collection.py` (sync method signatures); PyPI `anki` 26.5
file list (manylinux aarch64/x86_64 wheels); Anki forums
"authenticate (AnkiWeb login) without the GUI" (supported hkey path;
24.11+ restrictions); docs.ankiweb.net/sync-server.html + AnkiDroid/
AnkiMobile custom-server settings; lervag/apy (headless pylib
precedent); mochi.cards/docs/api (REST API, attachments, Pro-gated);
open-spaced-repetition/py-fsrs; rhasspy/piper VOICES.md (`sr_RS`
serbski_institut); edge-tts voice list (`sr-RS-*`, `hr-HR-*`).
