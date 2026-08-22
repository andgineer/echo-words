# Chat interface: Telegram vs self-hosted Mattermost — decision

Status: **a self-hosted Mattermost server is rejected as the user-facing
interface, on the analysis below. Do not re-open.** This document exists to
keep that option from being proposed again; the interface itself is settled
in `decision-interface.md`. The evaluation compares Mattermost against a
Telegram bot, because those were the two candidates it weighed — neither is
the interface now, and what survives here is why Mattermost is not one.

## The hypothesis that was tested

> Mattermost, hosted next to the backend on the same Oracle Cloud Free
> Tier instance, could simplify the architecture: the application gets a
> ready-made self-hosted chat interface and no longer depends on the
> external public Telegram service.

## Feature mapping (verified against Mattermost docs, 2026-07)

What maps cleanly:

| What a chat interface has to provide | Mattermost equivalent | Verdict |
|---|---|---|
| Forum topics = language → deck | One channel per language | Equivalent, arguably cleaner |
| Long polling (no public IP on backend) | Outbound WebSocket client | Equivalent |
| Placeholder-edit streaming | `PATCH /posts/{id}` | Equivalent; laxer rate limits |
| HTML `<b>`/`<i>` + sanitizer, 4096-char limit | Native Markdown, ~16K limit | Simpler |
| User-ID whitelist | Server accounts | Better (real auth) |
| 24 h update retention while the backend is down | Full server-side history | Better — *while the server is up* |

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
channel routing, post/edit, attachments are the same volume of work a
Telegram integration takes). What it adds is an operated stack:
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

**Mattermost is not the interface.** Self-hosting it means operating a
stack in exchange for degrading exactly the capabilities a chat interface
was wanted for — inline buttons, voice messages and mobile push, the last
two partly paywalled — and adding an always-on node to run it on. What
self-hosting buys (data sovereignty, compliance, team use) is not among
this project's requirements. Revisit only if those requirements appear.

References: Mattermost plans/pricing (voice messages = Professional),
mobile push docs (HPNS licensed, TPNS non-production), interactive
messages docs (integration callback URL), all checked 2026-07-17.
