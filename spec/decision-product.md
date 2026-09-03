# Decision: the settled product decisions

The guard list. Every question below is answered, and the answers are
described as behaviour by `functional-description.md`, which stays the
source of truth on any conflict. This file exists so a session can check
that a question is already closed without carrying the argument through
the work again. **Do not re-open any of it.**

## Product decisions (all questions resolved — do not re-open)

- One successfully parsed unit submission creates one note about one selected
  sense; a text answer creates none. A bare word selects its most common sense,
  while explicit unit intent with context selects the retained contextual
  sense. The visible article and chips keep every target-language-distinct
  sense. There is no arbitrary sense-count ceiling.
- **The same word may be sent twice, and gets a second note.** There is no
  duplicate check. A sense chip is a new submission, so deduplication would
  refuse exactly the route by which another sense enters the deck. Equal bare
  sends making equal notes is the visible, undoable cost.
- **The card carries the wording the answer analysed — hardcoded, no config
  flag.** The raw submission remains the history and PWA-audio text. A suspected
  misspelling is corrected on the card rather than offered, because a note
  pairing the learner's spelling with another word's meanings and examples
  teaches a word no sentence on it contains; the entry names the carded word
  above the analysis and the card's own deletion removes it. Wording the judgement
  will not vouch
  for as used gets no card, no article and no audio: a model asked for a
  dictionary entry invents one for any well-formed string, so a unit submission
  is judged by a parallel call that asks nothing else. Asking apart is what makes
  the defence work, and it is measured: the same question inside the article call
  withholds a fraction of what it withholds on its own. Where an answer replaces
  the submission with a correction, that correction faces the same question, so a
  refusal is never discarded for a claim nothing has vouched for.
  Rarity is never a reason to refuse.
  **What cannot be verified is said, not hidden.** No judgement makes a model
  incapable of a confident article about a string nobody says, so the promise is not
  that a card never carries one — it is that unverified wording is never presented as
  verified. Two reference works outside the models are asked about the wording each
  note carries — a dictionary, for whether anyone wrote it down, and the encyclopedia,
  for whether anyone writes it — and the entry says so only where both come back
  empty, with the search that came back empty linked so the claim is checkable. A
  dictionary alone accuses set expressions no wiki carries, which is most of what a
  learner of Serbian submits; requiring the second source is what makes the warning
  mean something. A card the reader was warned about is the product working, not
  failing; a card that quietly teaches an invention is the failure. The check never
  withholds, because a false refusal costs more than a warning does.
  A declared misspelling is settled by the paid model, which is measurably better
  at spelling than the pool; a refusal is not sent to it, because the paid models
  withhold fewer coinages than the pool does. Ordinary wording reaches neither.
- **Every accepted note generates exactly four cards.** The bare word and its
  translations are asked both ways; the selected sense's sentence is asked
  once with all unit parts highlighted and once with them gapped. A short sense
  label appears on the two bare fronts only when the answer retains several
  senses. The model returns both finished sentence forms. For an exact submitted
  click the backend constructs them from the carried context; generated forms
  are sanitized and accepted only as matching transformations which retain
  context outside the unit. The backend does not infer generated morphology.
- Card 2 is intentionally bare translations plus the optional label. A bare
  translation may fit several source words, and the label disambiguates it.
  The gapped example is card 4, which asks the separate production-in-context
  question. The catalogue and measurements are in
  `decision-card-shapes.md`.

- **Anki without a GUI — final.** The backend maintains its own
  collection via the headless `anki` pylib and syncs it to AnkiWeb;
  AnkiConnect and Anki desktop are not part of the architecture. There
  is no pending-card queue — adds are in-process and cannot fail on
  connectivity; only the sync retries. The running app never resolves a
  required one-way full sync (protects the user's other decks); the
  operator's explicit note-type rebuild does, uploading, because the
  deletion it just confirmed exists in no other copy — and it merges
  AnkiWeb in before deleting, so that upload rolls nothing else back.
  Evaluated alternatives (GetSpace, Mochi, own FSRS, genanki):
  `spec/decision-spaced-repetition.md`.
- Anki sync to AnkiWeb runs automatically after additions,
  debounced and retried; `ECHOWORDS_ANKI_SYNC=false` turns it off.
- Lookup-only (the `?` prefix): analysis and audio, no Anki card. Its unit entry
  may still request deeper detail, but offers no deletion because there is no note.
- Deleting a card removes the note the entry in front of the reader created, and
  takes that note out of undo's reach as well. Undo removes what the last send
  created and is an explicit no-op after a lookup-only send — it never deletes a
  note that existed before — but no control offers it any more.
  A rebuild replaces the note the entry produced rather than adding a
  second one. Rebuild and detail use the stored unit headword and explicit
  unit intent; rebuild reuses card audio only while the NFC-normalized returned
  headword is exactly unchanged, including case. Both act per source language.
- Multiple source languages via the **language selector**; the
  selection determines the deck. One deck per source language from the
  languages config, no per-word switching and no guessing the deck from
  the word. A single target language for explanations
  (`ECHOWORDS_TARGET_LANG`, Russian default). Language is never
  auto-detected — the selection is authoritative; an unknown code gets
  a hint, not a guess.
- Accent: config-level (`ECHOWORDS_ACCENT` default, per-language override),
  applies to English audio, US default, one recording per card, no
  per-word choice.
- Answer formatting IS in v0.1: HTML `<b>`/`<i>` only, enforced by the
  server-side sanitizer — the only HTML the client ever renders.
- Everything submitted is voiced, a running text included. The PWA keeps that
  exact submitted-text audio; only an NFC-normalized, case-sensitive exact
  headword match can reuse it for Anki. A different dictionary headword gets
  separate audio. Submitted, context and newly known headword audio share one
  concurrent post-generation wait capped at ten seconds. The surrounding
  context is offered in the app alone. Missing submitted-text audio and missing
  card-headword audio are reported separately. Example sentences are never
  voiced (final).
- **TTS engines are settled by research, not deferred**
  (`spec/decision-tts.md`): Serbian → edge-tts (Piper's lone `sr_RS`
  model is Lower Sorbian, not Serbian — never use it; no other usable
  free local voice exists); English and German → Piper. One deployment
  target (Oracle E2.1.Micro, 1 GB + swap); Kokoro left the design with
  the laptop profile. Model downloads follow the config.
- Stats and status ARE in v0.1.
- v0.1 ships **two LLM backend kinds** behind one seam, both through
  llmbroker: the free-tier model pool (fast, streaming, un-metered; the
  default) and `api` — a paid, **opt-in, never-required** single frontier
  model called through llmbroker's *direct client*, declared in code by a
  curated catalog alias. Metered spend is bounded by
  `ECHOWORDS_API_DAILY_CAP` with automatic fallback to the free pool, so
  no metered API is ever required. Which backend is the default, and
  which languages route to which, was fixed by the **backend benchmark**
  (`spec/decision-llm-backend.md`): every v0.1 language starts on the free
  pool — measured, not guessed. A CLI coding agent is not one of the
  backends: it would need the laptop, which is not a deployment target
  (`spec/decision-interface.md`), and the paid direct client covers the
  quality role it was wanted for. So there is no agent-sandboxing surface
  anywhere — both backends are plain text→text calls with nothing to
  contain.
- Words are processed sequentially and in submission order (one worker
  over a FIFO queue) — no two submissions are in flight at once, in any
  language. Within one submission the article call and the parallel
  attestation call do run together: the reader is held until both have
  answered either way, so running them in sequence would add the judgement's
  latency to every word and buy nothing.
- **echo-words has no database.** The Anki collection is the only
  durable state; history is a bounded in-memory buffer, "added" stats
  are counted from the collection's own note ids, and the lookup-only
  counter, undo and correction state reset on restart. Losing any
  of it costs nothing, because every word that mattered is already a
  card — so there is no schema, no migrations, and nothing to back up
  or replicate.
- **It runs on the tenancy's second free-tier VM**, the otherwise idle
  box that holds dinary's Litestream replica — not on dinary's own VM.
  More headroom, and its own Tailscale node, so the app owns a
  hostname's root instead of negotiating an origin with a neighbouring
  PWA. Measured comparison, and the rules that box imposes:
  `decision-deployment.md`.
- **llmbroker state is its own directory, not dinary's database.**
  `home=` is already the plain-files option and is explicitly a
  disposable cache; sharing a SQLite store across processes is not
  supported by the driver as written (no WAL, no busy timeout), and
  would buy almost nothing since quality learning is keyed per
  operation. See `decision-deployment.md`.
- **The PWA and the deploy are ported from `dinary`, not invented.**
  dinary is the author's working PWA on the same Oracle Free Tier shape,
  reached the same way over Tailscale, on the same FastAPI + llmbroker
  stack — so echo-words takes its Vue 3 + Vite + `vite-plugin-pwa`
  build wiring, design tokens, client composables, and its `invoke`
  deploy tasks (systemd unit with the sandbox block and the
  `tailscaled` wait, swap provisioning, host hardening). This overrode
  an earlier "vanilla JS, no build toolchain" intent: the toolchain
  demonstrably fits the 1 GB instance because dinary builds there in
  production, and the workbox/PWA configuration is the part most
  expensive to re-derive by hand. **Ansible/Chef were considered and
  rejected** — their value is idempotency, inventory and roles, and the
  ported tasks are already idempotent while a single instance has no
  fleet to inventory. What was deliberately left behind: dinary's
  Litestream backup apparatus (there is no database to replicate), its
  Pinia store layer, and its receipt/catalog domain. The rejection
  argument is `decision-deployment.md`.
- **The PWA over Tailscale is the user interface — final.** A Telegram bot
  is rejected: Tailscale gives the same zero-ops ingress, and Telegram's
  24 h buffering rescues only the card, never the answer that was wanted
  now. A self-hosted Mattermost server is rejected too. Full analysis:
  `spec/decision-interface.md`,
  `spec/decision-chat-interface.md`. Tailnet membership is the only
  access control; the backend binds loopback and never handles TLS or
  auth.

## Out of scope — final, not deferred

Chat-platform interfaces (Telegram bots included), native mobile apps,
public internet exposure (the app lives inside the tailnet), multiple
**users** (multiple **source languages** with separate decks for the
single user ARE in scope), example-sentence audio, Docker,
configuration-management tooling for deployment (Ansible/Chef — see
`decision-deployment.md`).
