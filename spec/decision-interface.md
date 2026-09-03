# User interface: PWA over Tailscale replaces the Telegram bot — decision

Status: **decided 2026-08-16 — the user interface is a PWA (a single
static page served by the backend itself), reachable only inside the
owner's Tailscale tailnet. A Telegram bot is rejected as the interface.
Do not re-open without new requirements.**

## Context

`decision-chat-interface.md` (2026-07-17) settled "Telegram vs
self-hosted Mattermost" — Mattermost remains rejected on that analysis.
A minimal own web UI was dismissed there in one paragraph ("pays for
auth, hosting, distribution, and push") without the same rigor, so the
present question — Telegram bot vs a small PWA — had never actually been
evaluated. The owner's requirements that frame it:

- add words from the phone **and** the computer;
- no native iOS app;
- a maximally light backend whose home is an always-on Oracle Cloud
  Free Tier micro instance (1 GB RAM);
- single user (family use dropped — see below).

## Why Telegram's strongest advantages dissolved

1. **Zero-ops ingress.** The bot's long polling needed no public IP,
   domain, TLS, or auth code — the decisive argument against any web UI.
   Tailscale removes it symmetrically: `tailscale serve` publishes the
   backend's localhost port as HTTPS **inside the tailnet only**, with an
   automatic certificate. No domain, no open ports, no login page —
   tailnet membership *is* the authentication, at zero code. Checked
   against the owner's situation: no other VPN occupies the iPhone's
   single personal-VPN slot, and there is exactly one user, so nobody
   else needs tailnet onboarding.
2. **24 h message buffering.** Telegram would deliver words sent while
   the backend was down. But buffering only rescues the *secondary*
   effect (the word eventually becomes a card) — never the *primary* one
   (the explanation, wanted right now; with the backend down Telegram
   shows no answer either). The product's value is the immediate answer,
   so an answer hours later is worth little. The card half is covered in
   the PWA by a small local resend queue (words that failed to send are
   kept in browser storage and re-sent on the next successful open).
3. **Mobile push.** Push mattered when answers took tens of seconds
   through CLI coding agents. The llmbroker pool answers in seconds while
   the user is looking at the screen; push is not needed for the core
   flow.

## What the PWA wins

- **Setup UX.** The supergroup + forum topics + BotFather privacy-mode +
  `topic_id`-per-language configuration — the clumsiest part of the
  Telegram design — collapses into a language selector on the page.
- **No platform-fighting code.** The placeholder-edit streaming bridge
  with Telegram's edit rate limits, the sanitizer targeting Telegram's
  HTML parser, the 4096-char message limit, the 64-byte `callback_data`
  gymnastics, and the `python-telegram-bot` dependency all disappear.
  Streaming becomes a plain SSE feed into the page; the correction
  button, undo/redo, stats and status become ordinary UI controls backed
  by small API endpoints.
- **No external service in the interface layer.** The stack is fully the
  owner's own (matching the llmbroker choice on the LLM side).
- **A history view.** Recent words with their finished analyses are
  served from the backend's word log, so a reload, an SSE reconnect, or
  a second device never loses an answer — something chat scrollback gave
  implicitly and the PWA now gives explicitly.

The core of the system is untouched: the LLM contract, card building,
headless Anki integration, and the audio chain are interface-agnostic.

## Accepted costs

- A small frontend to write and maintain. Cheaper than it looks: the
  author's `dinary` is an already-working PWA on the same Oracle shape,
  reached the same way over Tailscale, so its design system, PWA build
  wiring and client composables were ported rather than invented.
  Streaming is the one part with no precedent there.
- **Tailscale becomes a system dependency** on the phone, the computer,
  and the server. Its client must be connected for the app to work.
- **iOS share sheet:** Safari does not implement Web Share Target, so
  the PWA cannot appear in "Share" directly. Copy/paste works as
  anywhere; the documented share-sheet path is a one-time iOS Shortcut
  that POSTs the shared text to the API over the tailnet.
- **SSE drops when Safari backgrounds the tab.** Mitigated by the
  server-side history: on reconnect the client re-fetches recent
  entries, including the accumulated text of an in-progress generation —
  nothing is lost.
- **Backend down ⇒ interface down.** Accepted per the buffering analysis
  above; the local resend queue still turns words submitted during an
  outage into cards.

## The interface language is the client's, and so is every wording

The PWA carries an interface-language selector (English and Russian) whose
choice is remembered per browser. It governs the whole interface, including
text about work the backend did — the Anki result on an answer, a failed
analysis, a missing recording.

**The client owns the wording; the API carries codes, not sentences.** An
answer's Anki outcome travels as a status code and the client renders the
label. Two reasons, in order of weight:

- Word history outlives the request that created it. A sentence rendered by
  the backend would freeze at the language that was active when the card was
  made, so switching the selector would leave older entries in the old
  language. A code re-renders with the rest of the interface.
- Much of this text never passes through a response the client can put a
  language on: results arrive over SSE, which carries no request headers.

Two kinds of text stay on the backend, because no code can stand in for
them: the analysis itself, and a foreign error quoted verbatim — what Anki
or a provider reported. They are shown as they came.

The backend keeps a message catalogue only for what it must render in the
response itself: validation refusals of a submitted word. Those are answers
to one request, never stored, and the request carries `Accept-Language` set
from the selector.

## The words screen is a rail of words over one swipeable card

Status: **decided 2026-09-03 against an interactive design canvas.**

The screen was first built for one word at a time with a feed of finished
answers under it. In use there are a couple of dozen entries, usually one
studied language, and a reader who wants the word they read a minute ago.
A feed answers that by making them scroll past every expanded card in
between; a carousel with dots answers it no better past three entries,
because a dot cannot say which word is behind it.

**The rail is the index and the card is the reader.** A horizontal strip of
word chips sits over a single card. The eye scans words; one tap opens any of
them. There is no page counter and no arrows: position is which chip is
centred and highlighted, which says more than a number and does not duplicate
the swipe.

**Languages are buttons above the whole screen, not a dropdown inside the
form.** There is rarely more than one studied language, so two clicks to
change something that is usually fixed is wrong, and a `<select>` hides how
many there are. The row sits above everything because it filters the input
*and* the rail. With one language it is a single full-width button that still
names the language, and the pencil beside it stays reachable.

**Every tap is answered before the network is.** A press state, then motion,
then — where a model is being asked — a progress strip, a line saying roughly
how long it takes, and a pulsing dot on that word's chip, so the reader can
swipe away and still see the work running. This holds for the fast free call
as much as for the ten-second paid one. A switch is always a movement: the
card arrives from the side it came from, because a tap that silently swaps
text reads as nothing having happened.

**Nothing on the card is said twice.** The model name sits in its top right;
the language is already named by the active button; the bottom meta line is
gone. A sentence card shows no card status — the presence of word chips and
the absence of a delete button say it. The chips carry no caption either:
"tap one to analyse it" is read once in a lifetime and occupies space forever,
and filled pills that look pressable say it instead. What the chips keep is
the reason under each of them: two sense chips of the same word are told apart
by nothing else.

**Deletion is per card, not "undo the last one".** Undo asks the reader to
remember which word was last; the card in front of them is what they mean. It
is offered only where a note exists, asks its question inside the card, and
leaves the analysis on the screen. Because every card carries it, the
"lookup only" checkbox earned nothing: Anki calls are not worth saving, and a
reader who has just typed a word does not yet know whether it is worth
learning. The `?` prefix keeps that path for whoever wants it at no cost in
pixels.

**One paid action, named for where the answer lands.** "The full entry" is the
extended prompt — every sense, origin, shades, usage — and it opens inside the
card without touching Anki. Rewriting an existing note with the paid model is
**deferred, not built**: the reader never sees the note, and the plain
translation a card needs is what the free model gets right the first time. The
endpoint and its pipeline path stand; only the button went.

## The theme follows the system

Status: **decided 2026-09-03.** Pinning dark was never a decision, only a
default nobody revisited.

The dark values stay the base in `:root`, so a scoped block written against
them degrades to the old screen rather than to an unstyled one, and only the
tokens are overridden under `prefers-color-scheme: light`. Light darkens the
accent: white text on the brand `#e94560` reads about 3.9:1, under the 4.5:1
floor, where `#c81e42` reaches 5.6:1. The brand red is not to be restored
there.

The browser chrome follows through two media-queried `theme-color` tags. A
web-app manifest carries one colour and cannot be media-queried, so its
`theme_color` and `background_color` stay dark; they govern only the installed
app's splash.

## The language editor stops short of the prompt

Status: **decided 2026-09-03.**

Adding a language was a file edit and a restart, which is the wrong shape for
something a reader does from a phone. The editor covers everything they
actually do: add a language, remove one, and fix its name, deck, script, voice
engine, voice, dictionary code and accent.

**It exposes neither `api_model` nor `prompt_hints`, and refuses a request
carrying either.** Every field it does show is inert data with a visible,
immediate, reversible effect — a wrong deck name shows up on the next card, a
wrong voice is heard at once. Those two are not:

- `prompt_hints` is interpolated into the prompt, so the string in the
  languages table is literally part of what the model is asked. A bad hint
  degrades every later answer for that language quietly, and only a bench run
  would find it. Keeping it in the repository keeps a change to it under
  review and under the bench gate, instead of turning it into a text box with
  nothing to catch it.
- `api_model` builds the broker's direct map when the process starts, so
  writing it would mean rebuilding the broker under a live app. Leaving it out
  means no write can invalidate the broker.

Both are also set once per language by whoever tunes prompts, not by whoever
adds a language. The editor round-trips them untouched, so saving a voice can
never silently drop a hint. Tuning either stays a configuration edit and a
restart: that is the intended split, not a gap to close later.

Removing a language never deletes its Anki deck — the cards are the reader's,
and the confirmation says so — and the last remaining language cannot be
removed, because the table cannot be empty. Both deletions ask inside the row
they came from; neither uses a modal or a `confirm()`.

## Consequences

- The backend's home is the **always-on micro instance**; the laptop is a
  development environment, not a deployment target. Nothing that needs a
  laptop is part of the design — which rules out a CLI coding agent as an
  LLM backend, the paid llmbroker direct client covering that quality
  role, and rules out any TTS engine too heavy for the instance (see
  `decision-tts.md`).
- Multiple **users** were already out of scope; the tailnet-as-auth
  model additionally assumes the single owner.
- If the UI ever needs to grow (review exercises, richer views), the
  growth path is more of the same page — no Telegram Mini App, no app
  store, no separate platform.

References: Tailscale Serve docs (tailnet-only HTTPS with automatic
certificates); Apple iOS one-active-personal-VPN behavior; Web Share
Target API support tables (absent in Safari/iOS); iOS Shortcuts
"Receive input from Share Sheet" + "Get Contents of URL" (the POST
workaround). Why a self-hosted Mattermost server is not the interface:
`decision-chat-interface.md`.
