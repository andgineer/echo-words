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
