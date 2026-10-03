You are installing echo-words, a self-hosted vocabulary app, for the person you are
talking to. When you are done, an Oracle Cloud Always Free VM runs the app, it is
reachable only inside the user's private Tailscale network at
`https://echo-words.<tailnet>.ts.net/`, the user's phone opens it as a home-screen
app, and the cards it makes reach the user's AnkiWeb account. The server side is
free; one paid key is optional.

If you are reading this as a web page, get the exact text first — a page fetched
through a summarising tool loses details these steps depend on:

```bash
curl -fsSL https://raw.githubusercontent.com/andgineer/echo-words/main/docs/includes/agent-install.md
```

## How to work with the user

- The user has read nothing but the one-line prompt they gave you. Everything they
  need to know comes from you, in the language of that prompt.
- Begin with a short overview: what you will set up, which steps only they can do,
  that you will ask their approval for commands as you go, and what they need at
  hand — a credit or debit card for Oracle's identity check (Always Free is never
  charged), their phone, a Google account, and an AnkiWeb account (free at
  <https://ankiweb.net>, if they have none yet). Reviewing the cards on an iPhone
  takes AnkiMobile, a one-time purchase; AnkiDroid on Android and AnkiWeb in a
  browser are free.
- Hand them one step at a time: exactly which page to open, what to click or type,
  and what to tell you back. Wait until they say it is done before going on.
- Between their steps, say in a sentence what you are about to do, then report what
  happened.
- Never ask for a password or an API key in the chat, and never print the keys file:
  either would stay in the conversation's record. Secrets go into a file on their
  computer (step 6), and you check that it is filled without printing it.
- When something fails in a way these instructions do not cover, tell the user what
  happened and what you propose before you do it.

## What the user already has

Before step 1, ask what they already have, and skip what is done:

- **An Oracle Cloud account**: skip step 3.
- **A Tailscale account**: skip creating it in step 5, but still have them check that
  HTTPS Certificates are on. Their phone may already have the Tailscale app.
- **An AnkiWeb account**: nothing to create.
- **An earlier echo-words install**: a checkout whose `.deploy/.env` names a host.
  It is at `~/echo-words` unless they put it elsewhere, so ask. Work from that
  checkout instead of cloning another: its keys are already filled in. If
  `git status` there shows changes, or it is not on `main`, ask before you pull.
  Read the host it names with `grep '^ECHOWORDS_DEPLOY_HOST=' .deploy/.env`, check
  with `ssh <host> true` whether that VM answers, and ask which of three cases this
  is:
    - **a session that stopped partway** — a usage limit, a closed app: continue
      from the first step not done. If `.deploy/old-vm/` exists, it was a move;
      `.deploy/old-vm/host` holds the old VM's address.
    - **an update of the same VM**: in the checkout, `git pull --ff-only`,
      `uv sync`, `uv run inv deploy --ref=main`, then step 8; nothing else
    - **a move to a new VM**, because the old one is gone or being replaced: go
      through the steps, following their **Moving from an old VM** notes, with
      `<old-host>` the host the keys file names now

Below, `<checkout>` is that checkout, or `~/echo-words` for a first install.

## This is not a development task

The checkout contains `AGENTS.md` and `CLAUDE.md` for developers changing the code.
Their rules do not apply to an install, an update or a move: do not run the lint,
test or benchmark commands they require, and do not change any tracked file. The
user asking you for one of these is their approval to set up and deploy to their own
VM.

## 0. Check where you are running

- You need a shell on the user's own computer, because the checkout and its keys
  stay there: every later update runs from it. If you run in a remote sandbox or a
  cloud session, stop and tell the user to start you on their computer instead.
- Run `uname -s`. `Darwin` or `Linux` (WSL included) — go on. Anything else, such as
  Git Bash, MSYS or PowerShell on Windows, cannot run the deploy commands. Tell the
  user to install WSL: run `wsl --install` in PowerShell opened as administrator,
  restart, and finish the Ubuntu setup it opens. Then they start a new session of you
  inside WSL — in the Claude desktop app's Code tab, by choosing the WSL environment;
  in the Codex app, with Settings → Agent environment → Windows Subsystem for Linux
  and a restart of the app — and paste the same prompt again. Stop there.
- You need network access, including outbound ssh, and you will write to
  `<checkout>` and `~/.ssh`. If your sandbox asks the user to approve those, tell
  them to expect it.

## 1. Tools and the checkout

- You need `git`, `ssh`, `ssh-keygen`, `curl` and `uv`. Check each by running it
  (`git --version`, not `which git`: macOS ships a stub that only offers to install
  git). Install what is missing:
    - uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`. It is not on the PATH
      of the shell you have; your later commands may each start a new shell, so call
      it as `~/.local/bin/uv` or prefix them with `source ~/.local/bin/env &&`
    - git on macOS: `xcode-select --install`, which opens a dialog the user must
      confirm
    - on Linux or WSL: `sudo apt-get install -y git openssh-client curl` — when sudo
      needs a password your shell cannot type, have the user run that command
      themselves
- The checkout:
    - an earlier install's: `git -C <checkout> pull --ff-only`
    - none yet, and `~/echo-words` does not exist:
      `git clone https://github.com/andgineer/echo-words.git ~/echo-words`
    - `~/echo-words` exists but is not a checkout of
      `github.com/andgineer/echo-words`: stop and ask the user where to put it

    Run every later command from the checkout, starting with `uv sync`.
- If `uv sync` fails with `doesn't have a source distribution or wheel for the
  current platform` — an Intel Mac, or a Mac older than macOS 14 — the app's own
  dependencies cannot install here, but the deploy commands do not need them. Write
  every later `uv run inv …` as
  `PYTHONPATH=src uv run --no-project --with invoke --with python-dotenv --with pydantic-settings --with tomli-w inv …`.

## 2. The ssh key

Create a key used only for this VM, without a passphrase — the deploy commands run
without a terminal and cannot type one:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
test -f ~/.ssh/echo-words || ssh-keygen -t ed25519 -N "" -C echo-words -f ~/.ssh/echo-words
```

Tell the user it is their key to the VM. Only `~/.ssh/echo-words.pub` — the public
key — is ever shown or pasted.

## 3. The Oracle Cloud account — the user's step

Oracle allows one account per person and checks it against a card, so only the user
can create it. Send them to <https://signup.oraclecloud.com/> and tell them:

- their name and address must match the card's billing address exactly; a mismatch
  is the most common reason a signup is refused
- the card verifies identity, and may show a small temporary hold; the Always Free
  resources used here are never charged
- the **home region** they pick is permanent, and the VM has to be created in it, so
  they should pick one near them

Wait until they are signed in to the Oracle Cloud console.

## 4. The VM

**Moving from an old VM.** Do everything that needs the old VM now, before the new
one exists:

1. Ask whether anything besides echo-words runs on the old VM and is reached through
   Tailscale by its name. If so, the new VM cannot take that name without cutting
   the other thing off: it gets a name of its own in step 5, and the app on the
   phone is installed afresh in step 9 — the cards are all in Anki, only the app's
   list of past lookups starts empty.
2. Record the old VM, so a session that stops partway can resume:

    ```bash
    mkdir -p .deploy/old-vm
    echo '<old-host>' > .deploy/old-vm/host
    ```

3. If `<old-host>` answers, save what lives only on it — the languages the user set
   up in the app and the recordings behind the play buttons of past lookups — and
   its Tailscale name, the first label of `Self.DNSName`:

    ```bash
    scp <old-host>:/home/ubuntu/echo-words/data/languages.toml .deploy/old-vm/
    scp -r <old-host>:/home/ubuntu/echo-words/data/audio .deploy/old-vm/
    ssh <old-host> tailscale status --json
    ```

4. If `<old-host>` answers, stop the app there for good, so two servers never sync
   the same collection, and check that it sent every card to AnkiWeb. Ask the user
   to send no new words to it, wait until ten minutes have passed since their last
   one — the app sends cards to AnkiWeb up to five minutes after adding them — then:

    ```bash
    ssh <old-host> 'sudo systemctl disable --now echo-words'
    echo 'import sqlite3; db = sqlite3.connect("/home/ubuntu/echo-words/data/anki/collection.anki2"); sent = db.execute("select mod <= ls and scm <= ls from col").fetchone()[0]; print("all sent" if sent else "NOT SENT")' | ssh <old-host> python3
    ```

    On `NOT SENT`, start it again with
    `ssh <old-host> 'sudo systemctl enable --now echo-words'`, have the user send one
    word, and repeat ten minutes later.

5. A free account holds at most two VM.Standard.E2.1.Micro instances. Have the user
   check Compute → Instances: if two already exist, the new one cannot be created
   beside them — on Pay As You Go it would be billed. Then the old VM has to go
   first: only if nothing else runs on it (item 1), the user terminates it in the
   console. Otherwise stop and agree with the user which VM to give up.

**The network.** A new account has none, and the VM needs one that reaches the
internet. Have the user open Networking → Virtual cloud networks → **Start VCN
Wizard** → **Create VCN with Internet Connectivity**, and accept the defaults. An
account that already has such a network uses it.

The VM must be:

- a compute instance in the home region
- image **Canonical Ubuntu 22.04 Minimal** — the image the deploy runs on
- shape **VM.Standard.E2.1.Micro**, which is Always Free-eligible; the shape picker
  lists it under **Specialty and previous generation**
- in that network's public subnet, with **Automatically assign public IPv4 address**
  on
- given the contents of `~/.ssh/echo-words.pub` under **Paste public keys**
- otherwise left at the defaults

Oracle's console changes its layout, so go by these requirements rather than
remembered clicks. If you can operate the user's browser, you may fill in the form
yourself once they are signed in; show them what you chose before you press
**Create**. Otherwise guide them through it, field by field. This shape exists in a
single availability domain of the region, so if it is out of capacity there is
nothing else to pick: it has to be retried later. Never choose a shape that is not
Always Free.

When the instance shows **Running**, have the user tell you its public IP address —
it is not a secret. Make ssh use the key for it, and accept the VM's host key once,
because the deploy commands cannot answer that question:

```bash
printf '\nHost <IP>\n  User ubuntu\n  IdentityFile ~/.ssh/echo-words\n  IdentitiesOnly yes\n' >> ~/.ssh/config
chmod 600 ~/.ssh/config
ssh -o StrictHostKeyChecking=accept-new ubuntu@<IP> true
```

A new VM can take a minute or two before ssh answers: retry on a timeout or a
refused connection. `Permission denied (publickey)` is not a boot delay — the VM was
given a different key; check what was pasted in the form. If ssh still times out
five minutes after **Running**, the subnet has no route to the internet: on the
instance's page, follow its subnet to the virtual cloud network and add one — the
console offers **Connect public subnet to internet** for this.

## 5. Tailscale

The user's steps, one at a time:

1. Create a Tailscale account at <https://login.tailscale.com/start>. The Personal
   plan is free; signing in with Google is enough.
2. In the admin console's DNS page, <https://login.tailscale.com/admin/dns>, turn on
   **HTTPS Certificates**; MagicDNS has to be on too, and is on by default. The app
   is published with `tailscale serve`, which needs both.
3. Install the Tailscale app on their phone and sign in with the same account.

**Moving from an old VM** whose name the new one takes (step 4, item 1): two
machines cannot share a name, so the user first removes the old machine on
<https://login.tailscale.com/admin/machines> — the menu at the right of its row,
**Remove** — and you use the old name instead of `echo-words` in `--hostname=`
below. If the old VM keeps its name, the new one needs another: keep `echo-words`
unless that is the one taken, then pick a free one.

Your steps, on the VM:

```bash
ssh ubuntu@<IP> 'command -v curl >/dev/null || { sudo apt-get update && sudo apt-get install -y curl; }; curl -fsSL https://tailscale.com/install.sh | sh'
ssh ubuntu@<IP> 'sudo tailscale up --hostname=echo-words'
```

`tailscale up` prints a login link (`To authenticate, visit: …`) and then waits until
it is used. Run it in the background and read its output while it waits — a
foreground call shows you nothing until it ends. Give the user the link to open and
approve, and wait for the command to finish. Confirm with
`ssh ubuntu@<IP> tailscale status --json`: the first label of `Self.DNSName` is the
name the VM got. If it is not the one you asked for — Tailscale appends `-1` when the
name is taken — have the user remove any old machine still listed under that name,
then rename the new one on the machines page: the menu at the right of its row,
**Edit machine name**.

Then one more step for the user: on the same page, open the menu at the right of the
new VM's row and choose **Disable key expiry**. Otherwise the VM leaves their
network after 180 days and the app stops answering.

If an `apt` command on the VM reports `Could not get lock`, the new VM is installing
its own updates: wait five minutes and repeat the command.

## 6. The keys file

In `<checkout>`, create `.deploy/.env` from the template, unless it already
exists — never overwrite an existing one:

```bash
mkdir -p .deploy
[ -e .deploy/.env ] || cp .deploy.example/.env .deploy/.env
chmod 600 .deploy/.env
```

Point it at the new VM — this replaces the template's placeholder, or an earlier
install's old address — without opening the file:

```bash
sed -i.bak 's|^ECHOWORDS_DEPLOY_HOST=.*|ECHOWORDS_DEPLOY_HOST=ubuntu@<IP>|' .deploy/.env && rm .deploy/.env.bak
```

An earlier install's file already holds the user's secrets and settings: change
nothing else in it, and go to the check at the end of this step.

Ask the user which language the explanations and translations should be written in:
the language they think in, not the one they learn. Russian is the default; for any
other, set `ECHOWORDS_TARGET_LANG` to that language's English name, such as
`English` or `German`.

Then the user fills in their secrets. Open the file for them in an editor they can
use, in the background — on macOS `open -e <checkout>/.deploy/.env`, in WSL
`notepad.exe "$(wslpath -w <checkout>/.deploy/.env)"` — or tell them its full
path. Tell them what goes where:

- `GEMINI_API_KEY` — required. A free key from
  <https://aistudio.google.com/apikey>, **Create API key**.
- `ECHOWORDS_ANKIWEB_USER` and `ECHOWORDS_ANKIWEB_PASSWORD` — their AnkiWeb login,
  so that cards reach their decks. The first start downloads their AnkiWeb
  collection before adding anything, so existing decks are safe.

  Ask whether they already review in an Anki app without an AnkiWeb account. If so,
  they sign that app in to AnkiWeb and sync it **before** step 7. Otherwise their
  phone and the server each hold a collection AnkiWeb has never seen, Anki asks
  them to choose Upload or Download, and either choice discards one side.
- `OPENAI_API_KEY` — optional and paid. It adds a deeper article about a word on
  request; on the author's own use it costs about half a dollar a month. Leave it
  empty to stay at $0.
- `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ZAI_API_KEY` — optional and free. Each adds
  models that take over when Gemini is busy. They can be added later.

When they say it is saved, check that the required values are filled, without
printing them:

```bash
grep -cE '^(GEMINI_API_KEY|ECHOWORDS_ANKIWEB_USER|ECHOWORDS_ANKIWEB_PASSWORD)=.+' .deploy/.env
```

The count must be 3. Tell the user the keys stay in this file on their computer and
are copied to the VM by every deploy.

## 7. Set up and deploy

```bash
uv run inv setup-app --with-host-prep
uv run inv deploy --ref=main
```

`setup-app` runs once: it installs Node, uv and Tailscale, creates swap and hardens
the VM. `deploy` builds the app on the VM, starts it, and fails unless it answers its
health check within 30 seconds. Both take a long time on this small VM: run them in
the background, read their output as they go, and tell the user what is happening.
Both are safe to repeat.

- **Moving from an old VM** with saved files in `.deploy/old-vm/`: put them in place
  between the two commands, so the app's first start already has the user's
  languages and recordings:

    ```bash
    scp .deploy/old-vm/languages.toml ubuntu@<IP>:/home/ubuntu/echo-words/data/
    scp -r .deploy/old-vm/audio ubuntu@<IP>:/home/ubuntu/echo-words/data/
    ```

    Without them, the app starts with its default languages; tell the user to set
    theirs up again in the app.
- If `setup-app` prints a Tailscale link about enabling Serve or HTTPS, the
  certificates from step 5 are off. Give the user that link; if `setup-app` has
  already ended, run it again once they have approved.
- If `apt` reports `Could not get lock`, wait five minutes and repeat the command.
- The first start downloads the user's AnkiWeb collection, and a large one can
  outlast the health check. If `deploy` fails only there, wait a minute and run
  `uv run inv healthcheck`.
- Otherwise, if `deploy` fails, read its output and `uv run inv logs`, and explain
  to the user what went wrong. Never edit files on the VM; `deploy` refuses to run
  over changes there.

## 8. Check that it works

1. `uv run inv status` shows the service active, and `tailscale serve status` in its
   output shows the HTTPS address proxying to `http://127.0.0.1:8080`. Its lines
   about dinary replica files concern the author's own server; ignore them.
2. Read the app's address: `ssh ubuntu@<IP> tailscale status --json` gives it as
   `Self.DNSName`, without the trailing dot.
3. `ssh ubuntu@<IP> curl -fsS https://<address>/api/health` answers
   `{"status":"ok",...}`. That proves the private address and its certificate work.
   The first request can take several seconds while the certificate is issued.
4. `ssh ubuntu@<IP> curl -fsS http://127.0.0.1:8080/api/status` shows
   `pool.available` true, no entry of `pool.missing_keys` with `api_key_ref`
   `GEMINI_API_KEY`, and `anki.error` empty. On a first install `anki.last_result` is
   `ok`; after a later restart it stays empty until the next card is added. Expected
   and fine: the optional free keys left empty are listed in `pool.missing_keys`, an
   empty `OPENAI_API_KEY` in `pool.direct_missing_keys`, and with Gemini alone
   `pool.degraded` is true. Report anything else to the user.

## 9. The phone — the user's steps

Moving from an old VM under the same name, the app already on their phone keeps
working, past lookups included: they open it and send a word, then go on with item
5. If it opens blank, they close it fully and open it again — it still holds the old
server's pages for one load. Under a new name it is a new address: the old icon no
longer works, so walk them through the steps below.

Otherwise walk them through it one step at a time:

1. The Tailscale app is switched on, signed in with the same account, and lists the
   VM among its machines.
2. Open `https://<address>/` in Safari on an iPhone, or in Chrome on Android. Give
   them the exact address, and suggest sending it to the phone the way they usually
   do — a message to themselves, a note — so it can be tapped rather than typed.
3. Put it on the home screen. iPhone: **Share** (in recent iOS, under the **⋯**
   button), then **Add to Home Screen**. Android: the **⋮** menu, then **Add to
   Home screen** or **Install app**.
4. Open it from the home screen, choose the languages they learn in the app (it
   starts with English, German and Serbian), and send a word. A card is created.
5. To review the cards: Anki on the phone, signed in to the same AnkiWeb account —
   AnkiMobile on an iPhone, AnkiDroid on Android. New cards reach AnkiWeb within five
   minutes; if the first sync shows no `EchoWords` decks, wait and sync again.

If the phone cannot open the address, check in this order: Tailscale is on in the
phone's app, the phone and the VM are in the same account, and step 8 passed.

## 10. Finish

Tell the user, briefly:

- what now runs where, and the app's address
- that their keys live in `<checkout>/.deploy/.env`
- Oracle may stop a VM it considers idle, and a personal app is idle most of the
  time. If the app stops answering, they open the Oracle Cloud
  console → Compute → Instances → the VM → **Start**; the address and the data are
  kept. Converting the account to Pay As You Go is reported to prevent the stop, and
  stays free while only Always Free resources are used.
- how to update later: paste the same prompt into an agent again and ask it to
  update; these instructions cover it
- moving from an old VM that still exists: it can be terminated in Oracle's console
  once they are satisfied — unless something else runs on it. `.deploy/old-vm/` can
  then be deleted.
