# Spaced repetition without a running Anki GUI — research & decision

Status: **decided 2026-07-17 — adopted. AnkiConnect is replaced with
the headless Anki Python library (pylib) syncing to AnkiWeb; the user
keeps reviewing in AnkiDroid/AnkiMobile/desktop unchanged.**
**Verified end to end on 2026-08-17** on the target instance itself,
against the real AnkiWeb account and the real collection: the card
added by the server arrived on the phone with its audio. The operating
rules that verification produced are in `decision-deployment.md`; the
harness is `experiments/anki_headless_spike.py`.

## Why AnkiConnect is not the integration

AnkiConnect is an add-on inside Anki desktop: it only works while a full
Qt GUI application is running. That anchors the backend to the laptop,
makes the deployment heavy (a desktop app as a service dependency), and
rules out running echo-words as a small headless service on Oracle Cloud
Free Tier. The research question it forced: is there an architecture that

- needs no always-running GUI application,
- keeps the backend small (code, RAM, CPU),
- minimizes our own code,
- can run permanently on Oracle Cloud Free Tier,
- and keeps the user experience whole (cards appear automatically,
  reviews happen in a polished mobile app, audio plays on the card).

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
- **Full programmatic surface** — everything the backend needs from
  AnkiConnect exists as direct in-process calls on
  `anki.collection.Collection`: create decks and note types, add/find/
  delete notes, add media files, and **sync**:
  `sync_login(username, password, endpoint) -> SyncAuth`,
  `sync_collection(auth, sync_media)`, `sync_media(auth)`,
  `sync_status(auth)` (signatures confirmed against ankitects/anki
  main).
- **Fits Oracle Free Tier.** Version 26.5 publishes manylinux wheels
  for both x86_64 and aarch64. The realistically available shape is
  `VM.Standard.E2.1.Micro` — 1 GB RAM, x86_64 (the Arm A1.Flex shape is
  frequently out of capacity and is not assumed — see
  `decision-tts.md`); pylib fits it with a swap file behind the
  process. One Python service with an embedded Rust core — tens to a
  couple hundred MB of RAM, no GPU, no display server.
- **UX is fully preserved — this is the decisive property.** The
  backend maintains its own collection server-side and syncs it to
  **AnkiWeb**; the user's AnkiDroid / AnkiMobile / desktop sync from
  AnkiWeb (the debounced sync is what carries it there). Reviews stay in the Anki apps
  the user already knows: offline, FSRS scheduling, statistics, audio
  on the card. Nothing the user touches changes at all; only the
  invisible integration side changes.

What changes in the backend, compared to AnkiConnect:

- `anki.py` becomes a pylib wrapper instead of an httpx client — the
  same operations, in-process, no localhost HTTP hop. Model/deck
  bootstrap, deck-scoped dedup, `[sound:...]` media, two card
  templates: all map 1:1.
- **The pending queue shrinks to a sync-retry.** "Anki is not
  running" is not a state that exists: the collection is always
  available in-process, so adding a note cannot fail on connectivity.
  Only the AnkiWeb sync can fail transiently, and
  it is already debounced and non-blocking. The `pending_notes`
  machinery AnkiConnect would have needed (queue, drain task,
  queued-vs-added statuses) collapses; the word log and undo survive
  but simpler (a note is always either in the collection or not).

Risks, honestly:

1. **Sync auth from a script: closed.** Headless login against the
   real AnkiWeb works and returns a key that is reused for subsequent
   syncs — no GUI, no add-on, nothing gated. The 24.11+ tightening
   applies to add-ons, not to the library call.
2. **pylib API churn: smaller than assumed.** The surface this
   integration depends on has not changed at all across the releases
   from 23.12.1 to 26.08.1 — about two and a half years and eight
   releases; the changes before that were additive. The mitigation
   stands anyway (pin the version, upgrade deliberately), but the
   expected maintenance cost is near zero.
3. **One writer.** The server collection is written only by echo-words
   and only synced elsewhere — no concurrent-writer problem by
   construction (single-instance NFR).
4. **AnkiWeb dependency.** If the AnkiWeb path ever breaks, the
   fallback is Anki's **official self-hosted sync server** (built into
   the same package, a tiny process, docs.ankiweb.net/sync-server) on
   the same OCI instance; AnkiDroid and AnkiMobile both support a
   custom sync endpoint. Same architecture, one extra small always-on
   process, no AnkiWeb. A full round trip through it — server writes a
   note with media, an independent client reads it back — was verified
   headless on the target instance, so this is a switch-ready option
   rather than a theoretical one. Not the default because AnkiWeb
   costs zero ops and the user already has the account.
5. **AnkiWeb's terms of service — the one risk that cannot be
   engineered away.** The terms permit the browser and the four named
   apps (Anki, AnkiMobile, AnkiDroid, AnkiUniversal) and disallow
   other third-party clients, pointing programmatic users at
   AnkiConnect instead. That text is from 2018, before pylib was
   published as a standalone package, and it does not anticipate a
   process that runs Anki's own synchronisation code: on the wire our
   sync is indistinguishable from the desktop app's, and its volume is
   lighter than a normal user with three devices. So the practical
   exposure is low, but the sanction available to Ankitects is
   suspension of the account at their discretion, and it is not ours
   to appeal. This is the reason risk 4's self-hosted server is worth
   keeping ready: it removes AnkiWeb from the architecture entirely
   and costs one endpoint setting on the server and on the phone.

## Option C — own spaced repetition in the bot (Glosbe-style): viable, kept as the strategic alternative

The "don't integrate, implement" path the research asked to price out.
The scheduling itself is a solved problem — **`py-fsrs`**
(open-spaced-repetition/py-fsrs, the reference Python FSRS
implementation, `pip install fsrs`) gives the same modern algorithm
Anki itself now uses: `Scheduler.review_card(card, rating)` with
Again/Hard/Good/Easy, card state serialization to dict — a natural fit
for one SQLite table — which the app as built does not have. Reviews
happen **in the app's own interface**: it shows the card front (word +
pronunciation audio), a "show answer" control, then four grading
buttons; a daily note says how many cards are due per language. With
the PWA interface (`decision-interface.md`) such a review view would be
technically natural — which changes the cost of this option, not the
verdict below.

Cost/benefit vs Option B:

- **Pro:** the entire Anki surface disappears — no pylib, no AnkiWeb,
  no note types, no sync, no external anything. The backend becomes
  the whole product: one process, SQLite, py-fsrs (~pure-Python,
  trivial footprint). This is the true minimum for RAM/CPU/moving
  parts, and every future feature (custom exercises, LLM-generated
  quizzes) is easier because we own the review loop.
- **Con — the UX regression the goals forbid:** reviewing in the app
  is online-only; Anki apps give offline review, swipe flow, per-deck
  stats, and the user's existing habit and history. In-app review is a
  *different* product experience, not a drop-in replacement. It also
  adds the most *new* code of all options (review session flow,
  due-card querying, grading handlers, stats — a few hundred lines plus
  tests), whereas B mostly *deletes* code (the queue) — "minimize own
  code" favors B, not C, once a review UI is included.

Verdict: not for v0.1. Adopt only if the owner decides in-app review
is *desirable in itself* (always-with-you reviews in the same place
words are added); it is a product pivot, not an integration swap. B
does not block it later: FSRS state can be built from scratch or
imported, and the backend already owns card content.

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
discussion: it is AnkiConnect's flaw made heavier.)

## Effect on pronunciation audio

Leaving AnkiConnect does **not** disturb the audio pipeline — its
chain (dictionary recording → local Piper → edge-tts) is
independent of the card store:

- **Option B:** the mp3 goes into the server collection's media via
  pylib (`media.add_file` replacing AnkiConnect `storeMediaFile`) and
  the same `[sound:...]` field; `sync_collection(auth,
  sync_media=True)` carries it to AnkiWeb and on to the phone. Card
  audio behaves exactly as it does in the app.
- **Option C (if ever adopted):** audio is the same mp3 the app
  already stores and serves for the answer view, replayed at review
  time — no new storage or serving.
- **Platform-built-in voicing** (the "use the platform's own TTS"
  idea) exists in none of the candidates — Anki, Space, and Mochi all
  expect audio to be attached, not generated — so generating at card
  creation stays the design regardless of option. That is the right
  place anyway: generate once, play forever offline.
- **Serbian specifically** has no usable local voice: the lone Piper
  `sr_RS` dataset (`serbski_institut`) turned out to be **Lower
  Sorbian** miscatalogued under the Serbian locale and must never be
  configured — the later TTS research (`decision-tts.md`) settled
  Serbian on edge-tts (`sr-RS-SophieNeural` / `sr-RS-NicholasNeural`).
  Croatian (`hr-HR`) / Bosnian (`bs-BA`) voices remain a documented
  emergency fallback — phonetically close, but a wrong-language
  recording on a language-learning card is a quality cut to take only
  when everything else fails.
- **On the server:** Piper runs on CPU via onnxruntime on the 1 GB
  micro instance; the pragmatic configuration is Piper for languages
  with a usable local voice plus edge-tts (see `decision-tts.md` for
  the settled per-language matrix).

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
*reduces* net code (the pending queue collapses into the existing
debounced sync retry), keeps every card/audio/review behavior of the
current spec, and runs on Oracle Free Tier ARM today. Gate it with a
half-day spike (auth + add-note-with-audio + AnkiDroid arrival), the
way the backend benchmark gates the LLM choice. Keep the self-hosted Anki sync server as the
documented fallback if AnkiWeb auth proves fragile, and Option C as
the deliberate product pivot to revisit only if chat-native review
becomes a goal in itself — not as a way to avoid this integration,
which is now cheap.

## What this decision does not settle

- **Not decided here:** actually moving the backend off the laptop.
  B makes the backend location-independent; where it is hosted is settled
  by `decision-interface.md` — the always-on OCI micro instance, which
  the PWA interface requires.

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

References added by the 2026-08-17 verification: PyPI `anki` project
metadata (published by the Anki team, source ankitects/anki — the same
repository as the desktop app); ankitects/anki release tags 2.1.54
through 26.08.1 (API stability comparison); docs.ankiweb.net/syncing
(sync host names, six-month expiry of unused account data — which the
server's own syncing keeps at bay); ankiweb.net/account/terms (access
clause, last updated 2018-10-17).
