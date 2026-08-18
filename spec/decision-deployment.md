# Decision: where echo-words runs and how it gets there

Background for three settled deployment decisions — which host, which
deploy tooling, and where llmbroker keeps its state. The rules that
follow from them live in `implementation-plan.md`'s "Deployment"
section, which is what M6 and M8 execute; this file holds the reasoning
and the measurements, so the plan can stay instructions only. Settled —
do not re-open.

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
concern of its own because it has no database (the plan's "Durable
state" technology row).

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

Deployment is `invoke` tasks in `tasks/`, ported from dinary (the task
set is listed in the plan's "Deploy tasks"). **Configuration management
(Ansible, Chef, Salt) was considered and rejected** for this project:

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
