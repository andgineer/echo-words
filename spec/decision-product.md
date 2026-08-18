# Decision: the settled product decisions

The guard list. Every question below is answered; the answers are
implemented by `implementation-plan.md` and described as behaviour by
`functional-description.md`, which stays the source of truth on any
conflict. This file exists so an executing session can check that a
question is already closed without carrying the argument through the
plan. **Do not re-open any of it.**

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
  language, the key for dedup (deck-scoped), stats, undo,
  and the Anki `Word` field, compared case-insensitively. The same
  spelling in two languages is two notes in two decks. The LLM never
  silently swaps a misspelling: it analyzes the word as typed and returns
  an optional `suggestion`. When the suggestion differs from the input, a
  button on the entry switches to the suggested word (and back),
  re-running the analysis and replacing the note like a rebuild; only that
  path re-fetches audio. Because that tap turns LLM output into a
  canonical word, a `suggestion` must pass the same validation as typed
  input or it is dropped and no button appears. Rationale: a silently
  swapped card looks correct but is wrong and would poison the
  spaced-repetition deck without the user noticing — analyzing as-typed
  keeps the card's front equal to what the user sent, so a mistake is
  visible on the first review. There is deliberately no on/off setting;
  this behavior is the design, not an option.
- Every note produces two cards: recognition (source→target) and recall
  (target→source) — see M5. Still one note per word. The recall front
  carries, per meaning, a **gapped example** — that meaning's first
  example with the word replaced by `___` — because a bare translation
  often fits several source words and the reviewer cannot tell which one
  is being asked. The word is found by a plain case-insensitive
  whole-word match on the input as typed; where no example contains it
  verbatim the meaning shows its part of speech instead. Deliberately no
  stemming or per-language morphology: one rule that behaves the same in
  every configured language beats a better English front and an
  unpredictable Serbian one.
- **Anki without a GUI — final.** The backend maintains its own
  collection via the headless `anki` pylib and syncs it to AnkiWeb;
  AnkiConnect and Anki desktop are not part of the architecture. There
  is no pending-card queue — adds are in-process and cannot fail on
  connectivity; only the sync retries. A required one-way full sync is
  never resolved automatically (protects the user's other decks).
  Evaluated alternatives (GetSpace, Mochi, own FSRS, genanki):
  `spec/decision-spaced-repetition.md`.
- Anki sync to AnkiWeb runs automatically after additions,
  debounced and retried; `ECHOWORDS_ANKI_SYNC=false` turns it off.
- Lookup-only (the UI control or the `?` prefix): analysis and audio,
  no Anki card.
- Undo removes what the last send created and is an explicit no-op
  after a duplicate or a lookup-only send — it never deletes a note that
  existed before. A rebuild replaces the previous run's note instead of being
  blocked by the duplicate check. Both act per source language.
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
- Word/phrase audio only — example sentences are never voiced (final).
- **TTS engines are settled by research, not deferred to M6**
  (`spec/decision-tts.md`): Serbian → edge-tts (Piper's lone `sr_RS`
  model is Lower Sorbian, not Serbian — never use it; no other usable
  free local voice exists); English and German → Piper. One deployment
  target (Oracle E2.1.Micro, 1 GB + swap); Kokoro left the design with
  the laptop profile. Model downloads follow the config.
- Stats and status ARE in v0.1 (see M7).
- v0.1 ships **two LLM backend kinds** behind one seam, both through
  llmbroker: the free-tier model pool (fast, streaming, un-metered; the
  default) and `api` — a paid, **opt-in, never-required** single frontier
  model called through llmbroker's *direct client*, declared in code by a
  curated catalog alias. Metered spend is bounded by
  `ECHOWORDS_API_DAILY_CAP` with automatic fallback to the free pool, so
  no metered API is ever required. Which backend is the default, and
  which languages route to which, was fixed by the **M0 spike**
  (`spec/decision-llm-backend.md`): every v0.1 language starts on the free
  pool — measured, not guessed. A CLI coding agent is not one of the
  backends: it would need the laptop, which is not a deployment target
  (`spec/decision-interface.md`), and the paid direct client covers the
  quality role it was wanted for. So there is no agent-sandboxing surface
  anywhere — both backends are plain text→text calls with nothing to
  contain.
- Words are processed sequentially and in submission order (one worker
  over a FIFO queue) — no parallel LLM runs, even across languages.
- **echo-words has no database.** The Anki collection is the only
  durable state; history is a bounded in-memory buffer, "added" stats
  are counted from the collection's own note ids, and duplicate/lookup
  counters, undo and correction state reset on restart. Losing any
  of it costs nothing, because every word that mattered is already a
  card — so there is no schema, no migrations, and nothing to back up
  or replicate. See the "Durable state" technology row.
- **It runs on the tenancy's second free-tier VM**, the otherwise idle
  box that holds dinary's Litestream replica — not on dinary's own VM.
  More headroom, and its own Tailscale node, so the app owns a
  hostname's root instead of negotiating an origin with a neighbouring
  PWA. Measured comparison: `decision-deployment.md`; the rules that
  follow: the plan's "Rules the host imposes".
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
  fleet to inventory. The exclusion list is the plan's "Reuse from
  dinary"; the rejection argument is `decision-deployment.md`.
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
