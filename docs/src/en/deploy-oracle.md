# Deploy to Oracle Cloud

The supported target is an Oracle Always Free `VM.Standard.E2.1.Micro`: x86_64,
1 GB RAM, $0/month. A 2 GB swap file is a hard requirement. The systemd unit also
applies `MemoryHigh=400M` and `MemoryMax=500M`, so a runaway backend cannot take
the VM down. An Arm `A1.Flex` shape, when a region has capacity, lifts these
constraints but is not assumed.

Deployment is a set of `invoke` tasks run over ssh from your own machine.

## Join the tailnet first

Tailscale is the only front door for the app. Join the VM to your tailnet before
running setup:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Setup then configures `tailscale serve --bg 8080`, publishing the app at the
node's HTTPS root while uvicorn stays bound to `127.0.0.1:8080`. There is no
login page and no public-internet exposure. The node keeps whatever tailnet name
it already has.

## Secrets

```bash
mkdir -p .deploy
cp .deploy.example/.env .deploy/.env
chmod 600 .deploy/.env
```

`.deploy/` is gitignored. Set `ECHOWORDS_DEPLOY_HOST` to the VM's ssh
destination — its public address, as `ubuntu@203.0.113.10`: administration rides
public ssh, only the app is tailnet-only. An environment variable of the same
name overrides it for a one-off target. The deploy resolves the host before
building anything, so a missing or unedited value fails immediately rather than
after a frontend build.

Fill in the provider keys and AnkiWeb credentials as described in
[Configuration](configuration.md). They never enter the repository, a test
fixture, or a log line.

## Set up and deploy

```bash
inv setup-app --with-host-prep   # one-time, idempotent
inv deploy --ref=main
inv status
inv logs
```

`setup-app` installs Node 22, uv, and Tailscale, clones the repository, installs
and enables the service, provisions and activates a 2 GB
`/swapfile`, and verifies its format, active capacity, and single canonical
`/etc/fstab` entry. It creates a missing swap file and can grow an undersized
file that already has a swap signature, but fails without overwriting an existing
non-swap file, symlink, special path, or ambiguous fstab configuration. Swap
creation, activation, and verification failures stop setup.

The same pass hardens sshd and enables an explicit fail2ban sshd jail (3 failures
in 10 minutes, escalating 1-day bans capped at 30 days). The jail uses the
systemd backend and excludes Tailscale's `100.64.0.0/10` range, so tailnet
administration cannot ban itself; public ssh — the deploy path, and whatever else
reaches port 22 from the internet — is subject to it. Setup also disables
rpcbind and caps the system journal. It leaves the host firewall as it finds it:
the loopback and terminal-REJECT rules are re-asserted only when absent, and a
rejected change is skipped instead of failing the pass. It deliberately leaves an
existing checkout and running service untouched, and on a fresh host it does not
start the service.

`deploy` is the only code-and-PWA activation path. It pins the ref to a single
commit, so your local branch and any uncommitted work take no part in what ships —
the ref only has to exist locally and be pushed to the origin the VM clones from.
It requires a clean local checkout of the requested ref, checks out that same
commit on the VM, runs `uv sync --no-dev`, builds `_static/` **on the VM** with
`uv run --no-dev inv build-static`, syncs the secrets, starts or restarts the
unit, and fails unless `/api/health` answers within 30 seconds.

The remote checkout is inspected for modified tracked files and unexpected
untracked files both before checkout and before sync; deployment stops and prints
them instead of deleting anything. Gitignored runtime paths such as `.deploy/`,
`data/`, `.venv/`, and `_static/` stay in place.

!!! warning
    Never edit files on the server. The remote checkout is a deploy target, not a
    working copy — fix it in the repository and deploy again. Host changes belong
    in the `setup-app` / host-prep tasks so the VM stays reproducible from the
    repository.

## Checking the result

A deploy is finished only when its health poll passes. Confirm afterwards with
`inv status` and `inv logs`.

`inv status` reports the main process's current `VmRSS` and lifetime `VmHWM`
together, plus the service cgroup's `MemoryCurrent`, `MemoryHigh`, and
`MemoryMax`. It reports cgroup `memory.peak` separately only on kernels that
export that file; Ubuntu 22.04's 5.15 kernel may report it as unsupported. The
command fails if the service or unit is absent rather than accidentally reading
the root cgroup. The service's Tailscale readiness loop makes reboot startup
deterministic.

To build the PWA locally without deploying, use `inv build-static`.

## Releases

`inv ver-bug`, `inv ver-feature`, and `inv ver-release` bump the version in
`src/echo_words/__about__.py`, commit it, and push the commit together with its
`vX.Y.Z` tag. CI runs on that push and, when it succeeds, publishes the package
to PyPI and creates the GitHub release.
