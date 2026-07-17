# Chat interface: Telegram vs self-hosted Mattermost — decision

Status: **decided 2026-07-17 — Telegram stays; do not re-open without new
requirements.** This document records the evaluation of replacing Telegram
with a self-hosted Mattermost server as the user-facing chat interface,
and why the hypothesis was rejected.

## The hypothesis that was tested

> Mattermost, hosted next to the backend on the same Oracle Cloud Free
> Tier instance, could simplify the architecture: the application gets a
> ready-made self-hosted chat interface and no longer depends on the
> external public Telegram service.

## Why the premise fails: there is nothing to co-locate with

The current architecture has **no cloud instance at all**. The backend is
a single process on the user's laptop, pinned there by three anchors:

- **Anki desktop + AnkiConnect** at `127.0.0.1:8765` — cards can only be
  added locally;
- the **CLI coding agents** (claude / codex / antigravity) are
  authenticated under the user's flat-rate subscriptions on the laptop;
- the **local TTS models** (Kokoro / Piper) live in `WORDGRAM_DATA_DIR`.

Moving the backend to a cloud instance would require exposing the
laptop's AnkiConnect to the network — strictly worse. So a Mattermost
server on Oracle Cloud would not be "next to the backend": it would be a
**third node** (laptop + cloud VM + phone) where today there are two
(laptop + phone), with Telegram playing the always-available middleman
for free. The claimed consolidation is actually a topology expansion.

## Feature mapping (verified against Mattermost docs, 2026-07)

What maps cleanly:

| Telegram (current plan) | Mattermost equivalent | Verdict |
|---|---|---|
| Forum topics = language → deck | One channel per language | Equivalent, arguably cleaner |
| Long polling (no public IP on backend) | Outbound WebSocket client | Equivalent |
| Placeholder-edit streaming | `PATCH /posts/{id}` | Equivalent; laxer rate limits |
| HTML `<b>`/`<i>` + sanitizer, 4096-char limit | Native Markdown, ~16K limit | Simpler |
| User-ID whitelist | Server accounts | Better (real auth) |
| 24 h update retention while laptop is off | Full server-side history | Better — *while the server is up* |

What breaks or degrades:

- **Inline correction button** (the core UX of advisory autocorrection).
  Mattermost interactive buttons work by the *Mattermost server* POSTing
  to an integration URL — the backend would need an HTTP endpoint
  reachable **from the server**. A laptop backend is unreachable from a
  cloud VM, so the ✏️ button (and slash commands, same mechanism) would
  need a tunnel or a reactions-as-buttons workaround (`reaction_added`
  over WebSocket) — a materially cruder UX.
- **Voice messages** (pronunciation is a core feature). Mattermost voice
  messages are a **paid Professional-plan feature**; the free edition
  only posts an mp3 as a file attachment — playable, but not the
  tap-to-hear voice-message UX, especially on mobile.
- **Mobile push notifications** — the worst regression. Free self-hosted
  Mattermost has no production push service: HPNS requires a
  Professional/Enterprise license; the free TPNS is explicitly "not for
  production, no SLA"; the remaining option is compiling your own mobile
  app. "Send a word from the phone, get a push when the analysis
  arrives" — the everyday flow — just works on Telegram.

## Operational cost

Mattermost does not remove integration code (the WebSocket listener,
channel routing, post/edit, attachments are the same volume of work as
M1–M3 target for Telegram). What it adds is an operated stack:
Mattermost server + PostgreSQL upgrades/backups/migrations, a domain, a
TLS certificate, a public login page on the internet (today the backend
has **zero** inbound ports), and availability as our problem — "laptop
off → Telegram buffers 24 h" becomes "cloud VM down → the whole UI is
down, phone included". Oracle Always Free ARM is technically sufficient
(4 OCPU / 24 GB) but is known for capacity shortages and idle-instance
reclamation — a weak foundation for the single entry point of the app.

## As a long-term UI platform

A chat interface itself is a sound primary UI for the vocabulary
scenarios ahead (send-a-word, in-chat spaced repetition, AI interaction,
future exercises) — but Telegram is the *stronger* chat platform for
them, not the weaker one:

- **Inline keyboards** are the ideal primitive for review grading
  (Again/Hard/Good/Easy) and need no inbound connectivity; every
  Mattermost interactive element hits the callback-URL topology problem
  above.
- **Telegram Mini Apps** provide a full web UI inside the messenger — the
  incremental escape hatch if a future scenario outgrows plain chat
  (progress tables, interactive exercises), with no separate app,
  distribution, or auth. Mattermost's extension path (Go + React
  plugins, Apps framework) is an order of magnitude heavier and ties the
  investment to a niche platform.
- A custom web/mobile UI has the highest ceiling but pays for auth,
  hosting, distribution, and push — everything a messenger provides for
  free. It stays out of scope (final, per the functional description);
  if chat is ever outgrown, the next step is a Telegram Mini App, not a
  standalone app and not Mattermost.

## Decision

**Keep Telegram.** Self-hosted Mattermost would replace a free,
zero-ops, highly available external dependency with a self-operated
stack, while degrading exactly the capabilities the plan leans on
(inline buttons, voice messages, mobile push — partly paywalled) and
adding a third always-on node. The benefits self-hosting would buy
(data sovereignty, compliance, team use) are not among this project's
requirements. Revisit only if those requirements appear.

References: Mattermost plans/pricing (voice messages = Professional),
mobile push docs (HPNS licensed, TPNS non-production), interactive
messages docs (integration callback URL), all checked 2026-07-17.
