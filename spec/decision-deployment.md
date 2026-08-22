# Decision: where echo-words runs and how it gets there

Background for three settled deployment decisions — which host, which
deploy tooling, and where llmbroker keeps its state — and the rules
that host imposes on whatever runs on it. What the deploy actually
executes is `tasks.py`, with the operator's walkthrough in `docs/`.
Settled — do not re-open.

## Which host: the second free-tier VM, not dinary's

The Oracle Always Free tenancy holds **two** AMD micro instances. VM1
serves dinary; VM2 exists to receive dinary's Litestream replica over
SFTP. echo-words goes on **VM2**. Measured on both (2026-08-17; each
2 vCPU / x86_64 / 45 GB disk):

| | VM1 (dinary) | VM2 (replica) |
|---|---|---|
| RAM available | 570 MB of 956 | **627 MB of 956** |
| Swap in use | 193 MB of 1 GB | **82 MB of 1 GB** |
| Disk free | 35 GB | **41 GB** |
| App processes | dinary uvicorn 70 MB, litestream 18 MB | **none** |
| `tailscale serve` | root taken → `https://<node>/` | **unconfigured** |
| `systemd-journald` | 98 MB RSS, 3.9 GB of journals | 49 MB RSS |

VM2 wins on every axis, and one of them is architectural rather than
numeric: **it is a separate Tailscale node, so echo-words gets its own
hostname and the root path** — `https://<vm2>.<tailnet>.ts.net/`. On
VM1 it would have had to take a second HTTPS port (`--https=8443`) to
avoid sharing an origin with dinary, because dinary's service worker is
root-scoped with `clientsClaim` and a `navigateFallback` excluding only
`/api/`: it would claim navigations under any sibling path and answer
them with its own `index.html`. Two PWAs on one origin is a real
collision — on VM2 the question does not arise, and there is no port to
explain to the browser or to iOS.

Litestream is **not a service on VM2** — VM1 pushes files there over
SFTP — so nothing but the OS, tailscaled and fail2ban is resident. The
replica role costs disk, not RAM, and echo-words adds no replication
concern of its own because it has no database at all.

## Rules the host imposes

Every constraint below follows from the box rather than from a
preference: VM2 is a 1 GB `VM.Standard.E2.1.Micro`. (The Arm `A1.Flex`
shape — 2 OCPU / 12 GB for Always Free tenancies — is frequently
unobtainable per region and is not assumed; where it is available it
removes the memory constraints.)

- **A swap file is a hard setup requirement.** The web backend, the
  Anki pylib collection and a Piper inference peak coexist in 1 GB only
  with 1–2 GB of swap behind them, and with 41 GB free the insurance is
  cheap. Capping the journal (`SystemMaxUse=200M`) is worth doing on
  both VMs.
- **The unit stays memory-bounded anyway** — `MemoryHigh=400M` /
  `MemoryMax=500M`. Not to protect a neighbour, there is none, but so a
  runaway is killed as itself instead of taking the box down and
  stranding dinary's replica target. The budget is ~70 MB uvicorn plus
  the collection plus a Piper peak, and the pylib term is measured:
  103 MB peak on this box with the real collection.
- **Tailscale is the front door.** The backend binds `127.0.0.1:8080`
  and `tailscale serve --bg 8080` publishes that port at the node's
  tailnet root, so the backend itself never handles TLS or auth and
  tailnet membership is the access control.
- **The node keeps its `dinary-replica` tailnet name**, so the app is
  published at `https://dinary-replica.<tailnet>.ts.net/` and dinary's
  runbook keeps working unchanged. The odd-looking URL is seen once, at
  install, since the PWA lives on the home screen afterwards.
- **The host-level hardening pass belongs to this repo.** VM2 never
  received dinary's — `rpcbind` was still running there — so setup runs
  the host-prep pass on this box: packages, sshd hardening, fail2ban,
  swap, and the `rpcbind`/iptables step, all ported from dinary.
- **Outbound HTTPS to `*.ankiweb.net` must stay open.** Sync starts at
  `sync.ankiweb.net` and is redirected to a numbered shard whose name
  varies, so an egress rule pinned to one host would break syncing at a
  random moment. The Anki manual documents the wildcard.
- **The frontend is built on the server**, from the commit the deploy
  just checked out, so `_static/` and the backend can never come from
  two different revisions and no operator's working tree reaches the
  VM. VM1 runs the same Rollup build for dinary's heavier PWA on
  identical hardware next to a live uvicorn; echo-words builds 23
  modules into 82 KB.
- **If VM1 ever dies**, the documented recovery is to restore dinary
  onto VM2, where the two would then share a box — an emergency
  arrangement, and the reason the memory limits above stay in the unit.

## llmbroker state: its own directory, not dinary's database

echo-words keeps `home=ECHOWORDS_DATA_DIR/llmbroker`. **Sharing
dinary's llmbroker state was considered and rejected**, and the same
verdict holds even if the two ever land on one host:

- `home=` **is** the filesystem option: with no source argument
  llmbroker builds `FileRegistry(model_list_path(home))` +
  `FileStore(home/"store")` — plain files, no database. And that
  directory is explicitly a **cache** ("nothing here is authoritative,
  so no step may raise") — it is disposable, which is exactly the
  property this app wants everywhere else too.
- Pointing echo-words at dinary's `sqlite://` store would put **two
  processes on one SQLite file**, and llmbroker's sqlite driver opens
  its connections with neither WAL nor a `busy_timeout` — concurrent
  writers get `database is locked` immediately rather than waiting. It
  is not a supported multi-process configuration as the library stands.
  (Making it one — WAL plus a busy timeout — would be a reasonable
  llmbroker feature request, not something to work around here.)
- The benefit would have been small in any case: quality learning is
  keyed per `(model, operation)` and the two apps use different
  operation labels, so nothing transfers between them. Only pool
  backoff state would be shared, and llmbroker rediscovers that in a
  single failed call.
- It would also couple the two apps' upgrade schedules through a shared
  schema, replacing an independence that currently costs nothing.

Provider API keys may hold the same values in both `.deploy/.env`
files; that is fine, each process reads its own.

## Deploy tooling: invoke tasks over ssh, not Ansible/Chef

Deployment is `invoke` tasks in `tasks.py`, ported from dinary.
**Configuration management (Ansible, Chef, Salt) was considered and
rejected** for this project:

- The value those tools add over shell is **idempotency, inventory and
  roles**. dinary's tasks are already idempotent by construction
  (`test -d … ||`, `swapon --show | grep -qx /swapfile`,
  `systemctl enable --now`), and inventory/roles solve a fleet problem
  that **one instance running one app** does not have. There is a
  second VM in the picture, but it runs the other app and is
  provisioned by that repository's own tasks — two hosts owned
  separately, not a fleet to converge.
- Ansible would add a control-node dependency and a second mental model
  (YAML + modules) on top of the shell that still runs underneath;
  Chef additionally wants a server or chef-solo. That is real cost for
  no capability this project uses.
- Decisively: porting from dinary means **inheriting code that has
  already been debugged in production on this exact shape** — the
  systemd sandbox block, the `ExecStartPre` loop that waits for
  `tailscaled` (its comment records that `network.target` was found not
  to wait for it after a reboot), the swap provisioning, the sshd and
  fail2ban hardening. Re-expressing those in Ansible roles means
  re-deriving hard-won details in a different language: pure risk, zero
  gain.

Revisit only if echo-words ever grows past one host.
