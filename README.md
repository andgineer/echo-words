[![Build Status](https://github.com/andgineer/echo-words/workflows/CI/badge.svg)](https://github.com/andgineer/echo-words/actions)
[![Coverage](https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)
# echo-words

echo-words is a private, tailnet-only vocabulary assistant. It streams a compact linguistic
analysis, pronunciation, and examples for a word or phrase, then adds a two-direction note to
the source language's Anki deck. The server keeps no application database.

## Local setup

Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js 22 are required for development.

```sh
uv sync
npm --prefix webapp ci
mkdir -p ~/.echo-words
cp languages.example.toml ~/.echo-words/languages.toml
inv build-static
inv dev
```

`languages.toml` is the source of truth for source languages. Each `[languages.<code>]` table
names its display name, its own Anki `deck`, accepted `script`, dictionary code where available,
and its pronunciation engine/voice. `languages.example.toml` contains complete English, German,
and Serbian examples. Adding another source language is a configuration change, not a code
change.

Piper voices use `espeak-ng` for phonemization. Install the optional system package (for example,
`sudo apt install espeak-ng`) on machines configured with `tts = "piper"`; edge-tts languages do
not need it.

## AnkiWeb

Set `ECHOWORDS_ANKIWEB_USER` and `ECHOWORDS_ANKIWEB_PASSWORD` in the environment file and leave
`ECHOWORDS_ANKI_SYNC=true`. On the first run, the headless Anki collection performs a full
download of the existing account collection before local cards are added. The password is used
to obtain a sync key; the key is then kept under `ECHOWORDS_DATA_DIR`. A self-hosted Anki sync
server can be selected with `ECHOWORDS_SYNC_ENDPOINT` instead.

## Production host

The supported target is an Oracle Always Free `VM.Standard.E2.1.Micro`: x86_64, 1 GB RAM. A 2 GB
swap file is a hard requirement. The systemd unit also applies `MemoryHigh=400M` and
`MemoryMax=500M`, preventing a runaway backend from taking down the VM. An Arm `A1.Flex`, when a
region has capacity, removes these tight memory constraints but is not assumed.

Tailscale is the only front door for the app itself. Join the VM to the tailnet first, then setup
configures `tailscale serve --bg 8080`, which publishes the app at the node's HTTPS root while
uvicorn stays bound to `127.0.0.1:8080`. There is no login page or public-internet exposure. The
node keeps whatever tailnet name it already has; nothing here renames it.

```sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Keep outbound HTTPS unrestricted for `*.ankiweb.net`: AnkiWeb redirects sync to numbered shards,
so allowing only `sync.ankiweb.net` will fail intermittently.

Create the production secrets file and choose the SSH host:

```sh
cp .deploy.example/.env .deploy/.env
chmod 600 .deploy/.env
export ECHOWORDS_DEPLOY_HOST=ubuntu@<vm-public-ip>
```

`ECHOWORDS_DEPLOY_HOST` is an ssh destination, and it is the VM's public address — administration
rides public ssh, only the app is tailnet-only.

The llmbroker free pool needs provider credentials. Fill at least one of `GROQ_API_KEY`,
`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, or `ZAI_API_KEY`; filling all four gives the pool its full
failover set. The committed example includes signup links, and
`python -m llmbroker env freetier` prints the authoritative list for the installed llmbroker
release. The default paid fallback, `ECHOWORDS_API_MODEL=gpt-fast`, additionally needs
`OPENAI_API_KEY`; set `ECHOWORDS_API_MODEL=` to run only the unmetered pool. Keep all values in the
gitignored `.deploy/.env`, never in the committed example.

The real `.deploy/` is gitignored. On the target VM2, run the required host preparation on the
first setup; the command is idempotent and safe to repeat:

```sh
inv setup-app --with-host-prep
inv deploy --ref=main
inv status
inv logs
```

`setup-app` installs and enables the service without Node, provisions and activates a 2 GB
`/swapfile`, and verifies its format, active capacity, and single canonical `/etc/fstab` entry.
It creates a missing swap file and can grow an undersized file that already has a swap signature,
but fails without overwriting an existing non-swap file, symlink, special path, or ambiguous fstab
configuration. Swap creation, activation, and verification failures stop setup. The command also
hardens sshd and enables an explicit fail2ban sshd jail (3 failures in 10 minutes, escalating 1-day
bans capped at 30 days). The jail uses the systemd backend and excludes Tailscale's
`100.64.0.0/10` range, so tailnet administration cannot ban itself; public ssh — the deploy path,
and whatever else reaches port 22 from the internet — is subject to the jail. Setup also disables rpcbind and caps the system
journal. It leaves the host firewall as it finds it: the loopback and terminal-REJECT rules are
re-asserted only when absent, and a rejected change is skipped instead of failing the pass. It
deliberately leaves an existing checkout and running service untouched; on a fresh host it does
not start the service. `deploy` is the only code-and-PWA activation path: it requires a clean
local checkout of the requested ref, builds that exact commit's `_static/` locally, checks out the
same commit on the VM, runs `uv sync --no-dev`, syncs the bundle and secrets, starts or restarts
the unit, and fails unless `/api/health` answers within 30 seconds. The remote checkout is checked
for modified tracked files and unexpected untracked files both before checkout and before sync;
deployment stops and prints them instead of deleting anything. Gitignored runtime paths such as
`.deploy/`, `data/`, `.venv/`, and `_static/` remain in place. `inv status` reports the main
process's current `VmRSS` and lifetime `VmHWM` together, plus the service cgroup's
`MemoryCurrent`, `MemoryHigh`, and `MemoryMax`. It reports cgroup `memory.peak` separately only on
kernels that export that file; Ubuntu 22.04's 5.15 kernel may report it as unsupported. The same
command fails if the service/unit is absent rather than accidentally reading the root cgroup. It
shows the most recent files received in the dinary Litestream replica tree; check both after host
preparation and after a reboot. The service's Tailscale readiness loop makes reboot startup
deterministic.

### Production verification record

The release verification has not yet been recorded. Do not set the release version until one
real-host pass records the deployed commit and date, confirms repeated host preparation and the
health-gated deploy, reboots the VM, and verifies service recovery, phone access at the tailnet
root, iOS installation/offline-shell/API-network-only behavior, and continued dinary replication.
Record steady and peak RSS from `inv status` here and confirm they stay consistent with
`MemoryHigh=400M` and `MemoryMax=500M`.

No Node.js build runs on the 1 GB server. To build without deploying, use `inv build-static`.

## Install on iPhone and share text

Open the node's Tailscale HTTPS URL in Safari, tap Share, then **Add to Home Screen**. The installed
app opens standalone and its shell remains available offline; API requests are network-only.
Words submitted while the server is unreachable stay in a local FIFO queue and are retried on
the next app open or browser `online` event. Each browser submission carries a UUID that is stored
with the queue item. If the server accepted a POST but its response was lost, retrying that UUID
returns the original entry without repeating LLM or audio work. This receipt map is intentionally
in-memory like history, retains at most 4,096 accepted IDs for seven days, and resets on a backend
restart. A retry outside that window is a new request, but Anki's durable word/deck duplicate
check still prevents a second card.

For a share-sheet shortcut, create an iOS Shortcut that accepts text from the Share Sheet and save
Shortcut Input as the `Phrase` variable. Use **Match Text** with
`\p{L}(?:[\p{L}\p{N}'’-]*[\p{L}\p{N}])?` to make a list of word tokens. Like the PWA picker, this
requires a letter at the start and a letter or number at the end, while retaining an internal
apostrophe or hyphen: for example, `“don’t,”` becomes `don’t` and `'(go-over)'` becomes `go-over`.
If the list has more than one item, use **Choose from List** and set `Word` to the chosen token;
otherwise set `Word` directly to the only token. Build a Dictionary with `word`
set to `Word`, `lang` set to a configured code such as `en`, and `lookup_only` set to false. Only
in the multi-word branch, also set `context` to the original `Phrase`. Finally use **Get Contents
of URL** to POST that dictionary as JSON to
`https://<node>.<tailnet>.ts.net/api/words`. Tailscale must be connected. Add the shortcut to the
Share Sheet; a single word goes straight through, while shared prose requires choosing the word
and preserves the whole selection as context without exposing the service publicly.

## State and maintenance

echo-words has no database and needs no database backup. Only `ECHOWORDS_DATA_DIR` matters: it
contains the Anki collection, voice models, broker state, and audio. The collection is already
replicated through AnkiWeb, while history, undo state, and session counters are intentionally
in-memory and reset on restart.

`ECHOWORDS_DATA_DIR/audio/` keeps one small MP3 per looked-up word and has no cleanup policy in
v0.1. These cache files are safe to delete at any time: Anki reviews use the separate copy in the
collection's media directory.

## Development and release

```sh
inv pre
inv test
```

CI runs the Python 3.12/3.13 test matrix, frontend Vitest suite, and Ruff. Test reports are
published in [Allure](https://andgineer.github.io/echo-words/builds/tests/).

A release is one command: `inv ver-bug`, `inv ver-feature`, or `inv ver-release` bumps the version
in `src/echo_words/__about__.py`, commits it, and pushes the commit together with its `vX.Y.Z` tag.
CI runs on that push and, when it succeeds, publishes the package to PyPI and creates the GitHub
release. Do not release until PyPI publishing credentials are configured and the production
verification record above is complete.

Project documentation: [Echo Words](https://andgineer.github.io/echo-words/).

> Created with cookiecutter using [template](https://github.com/andgineer/cookiecutter-python-package)
