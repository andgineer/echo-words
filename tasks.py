import base64
import os
import shlex
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values
from invoke import Collection, Context, task

from echo_words.config import Settings


DOCS_PATH = Path("docs")
DOCS_SRC_PATH = DOCS_PATH / 'src'
WEBAPP_PATH = Path("webapp")
STATIC_PATH = Path("_static")
LANGUAGES_EXAMPLE = Path("languages.example.toml")
DEPLOY_ENV = Path(".deploy/.env")
DEPLOY_ENV_EXAMPLE = Path(".deploy.example/.env")
REPO_URL = "https://github.com/andgineer/echo-words.git"
REMOTE_ROOT = "/home/ubuntu/echo-words"
REMOTE_DATA = f"{REMOTE_ROOT}/data"
SERVICE_NAME = "echo-words"

SYSTEMD_UNIT = f"""\
[Unit]
Description=echo-words vocabulary assistant
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory={REMOTE_ROOT}
EnvironmentFile={REMOTE_ROOT}/.deploy/.env
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do tailscale ip -4 >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
ExecStart={REMOTE_ROOT}/.venv/bin/uvicorn echo_words.api:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
MemoryHigh=400M
MemoryMax=500M
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={REMOTE_DATA}
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
"""


def get_allowed_doc_languages():
    """Detect languages as subfolders in docs/src/

    Ensure `en` is always first.
    """
    return ['en'] + [f.name for f in DOCS_SRC_PATH.iterdir() if f.is_dir() and f.name != "en"]


ALLOWED_DOC_LANGUAGES = get_allowed_doc_languages()
ALLOWED_VERSION_TYPES = ["release", "bug", "feature"]



@task
def version(_c: Context):
    """Show the current version."""
    with open("src/echo_words/__about__.py", "r") as f:
        version_line = f.readline()
        version_num = version_line.split('"')[1]
        print(version_num)
        return version_num


def ver_task_factory(version_type: str):
    @task
    def ver(c: Context):
        """Bump the version."""
        c.run(f"./scripts/verup.sh {version_type}")

    return ver


@task
def reqs(c: Context):
    """Upgrade requirements including pre-commit."""
    c.run("pre-commit autoupdate")
    c.run("uv lock --upgrade")
    

@contextmanager
def docs_rendered(language: str):
    """Render docs sources for language specified.

    Copy language agnostic assets from en to non-en folders.
    Substitute language and site dir in config copy.

    Returns config copy path.
    """
    config_template_path = DOCS_PATH / "mkdocs.yml"
    common_path = DOCS_PATH / "common"
    src_path = DOCS_SRC_PATH / language

    build_docs_path = Path('build') / "docs"
    build_config_path = build_docs_path / "mkdocs.yml"
    build_src_path = build_docs_path / "src" / language
    site_dir = Path("site") if language == "en" else Path("site") / language

    config = config_template_path.read_text()
    config = config.replace("LANGUAGE", language)
    config = config.replace("SITE_DIR", str(site_dir))

    build_docs_path.mkdir(parents=True, exist_ok=True)
    build_config_path.write_text(config)
    shutil.rmtree(build_src_path, ignore_errors=True)
    shutil.copytree(src_path, build_src_path)
    if common_path.is_dir():
        shutil.copytree(common_path, build_src_path, dirs_exist_ok=True)
    yield build_config_path


def docs_task_factory(language: str):
    @task
    def docs(c: Context):
        """Docs preview for the language specified."""
        with docs_rendered(language) as config_copy_path:
            port = 8001
            c.run(f"open -a 'Google Chrome' http://127.0.0.1:{port}")
            c.run(f"zensical serve --config-file {config_copy_path} --dev-addr localhost:{port}")
    return docs


@task
def build_docs(c: Context):
    """Build docs in docs/site/."""
    for language in ALLOWED_DOC_LANGUAGES:
        with docs_rendered(language) as config_copy_path:
            c.run(f"zensical build --config-file {config_copy_path}")


@task
def uv(c: Context):
    """Install or upgrade uv."""
    c.run("curl -LsSf https://astral.sh/uv/install.sh | sh")


@task
def pre(c):
    """Run pre-commit checks"""
    c.run("pre-commit run --verbose --all-files")


def _run_build(c: Context):
    if not WEBAPP_PATH.is_dir():
        raise RuntimeError(f"Cannot build the PWA: {WEBAPP_PATH}/ is missing.")

    lock = WEBAPP_PATH / "package-lock.json"
    node_lock = WEBAPP_PATH / "node_modules" / ".package-lock.json"
    needs_install = (
        not node_lock.exists()
        or not lock.exists()
        or lock.stat().st_mtime > node_lock.stat().st_mtime
    )
    if needs_install:
        c.run(f"npm --prefix {WEBAPP_PATH} ci --no-audit --no-fund")

    c.run(f"npm --prefix {WEBAPP_PATH} run build")
    index = STATIC_PATH / "index.html"
    if not index.is_file():
        raise RuntimeError(f"The Vite build did not produce {index}.")
    print(f"Built {STATIC_PATH}/")


@task(name="build-static")
def build_static(c: Context):
    """Build the Vue 3 PWA from webapp/ into _static/. Run after any webapp/ change."""
    _run_build(c)


def _deploy_host() -> str:
    """Read the ssh destination from `.deploy/.env`, as dinary does; env overrides it."""
    override = os.environ.get("ECHOWORDS_DEPLOY_HOST", "").strip()
    if override:
        return override
    if not DEPLOY_ENV.is_file():
        raise RuntimeError(
            f"Missing {DEPLOY_ENV}. Copy {DEPLOY_ENV_EXAMPLE} to it and set "
            "ECHOWORDS_DEPLOY_HOST to the VM's ssh destination, for example "
            "ubuntu@203.0.113.10."
        )
    host = (dotenv_values(DEPLOY_ENV).get("ECHOWORDS_DEPLOY_HOST") or "").strip()
    if not host or "<" in host:
        raise RuntimeError(
            f"Set ECHOWORDS_DEPLOY_HOST in {DEPLOY_ENV} to the VM's ssh destination, "
            "for example ubuntu@203.0.113.10."
        )
    return host


def _ssh(c: Context, command: str) -> None:
    """Run a quote-heavy remote script without interpolating it into the remote shell."""
    encoded = base64.b64encode(command.encode()).decode()
    c.run(f"ssh {_deploy_host()} 'echo {encoded} | base64 -d | bash'")


def _upload_service(c: Context) -> None:
    encoded = base64.b64encode(SYSTEMD_UNIT.encode()).decode()
    _ssh(
        c,
        f"echo {encoded} | base64 -d | sudo tee /etc/systemd/system/{SERVICE_NAME}.service "
        ">/dev/null && sudo systemctl daemon-reload",
    )


def _sync_deploy_env(c: Context) -> None:
    if not DEPLOY_ENV.is_file():
        raise RuntimeError(f"Create {DEPLOY_ENV} from {DEPLOY_ENV_EXAMPLE} before deploying.")
    _ssh(c, f"mkdir -p {REMOTE_ROOT}/.deploy")
    c.run(f"scp {DEPLOY_ENV} {_deploy_host()}:{REMOTE_ROOT}/.deploy/.env")
    _ssh(c, f"chmod 600 {REMOTE_ROOT}/.deploy/.env")


def _health_check(c: Context) -> None:
    _ssh(
        c,
        "for i in $(seq 1 30); do "
        "if out=$(curl -fsS http://127.0.0.1:8080/api/health 2>&1); then "
        'echo "$out"; exit 0; fi; sleep 1; done; '
        'echo "health check failed after 30s: $out" >&2; exit 1',
    )


def _resolve_commit(c: Context, ref: str) -> str:
    """Pin the ref to one commit so the server cannot race a moving branch."""
    revision = shlex.quote(f"{ref}^{{commit}}")
    return c.run(
        f"git rev-parse --verify --end-of-options {revision}",
        hide=True,
    ).stdout.strip()


def _remote_deploy_script(commit: str) -> str:
    """Check out a revision only when no remote source could override it."""
    dirty_check = (
        "dirty=$(git status --porcelain --untracked-files=normal); "
        'if [ -n "$dirty" ]; then '
        "echo 'Refusing to deploy over remote working-tree changes:' >&2; "
        'printf "%s\\n" "$dirty" >&2; exit 1; fi'
    )
    return (
        f"set -euo pipefail; cd {REMOTE_ROOT}; "
        f"{dirty_check}; "
        f"git fetch origin {commit}; git checkout --detach {commit}; "
        f'test "$(git rev-parse HEAD)" = {commit}; '
        f"{dirty_check}; "
        "source /home/ubuntu/.local/bin/env; uv sync --no-dev; "
        "uv run --no-dev inv build-static; "
        f"install -d -m 700 {REMOTE_DATA}"
    )


def _swap_prep_script(
    swap_path: str = "/swapfile",
    fstab_path: str = "/etc/fstab",
    proc_swaps_path: str = "/proc/swaps",
) -> str:
    """Provision the required swap without overwriting an ambiguous existing path."""
    return f"""\
SWAP_PATH={shlex.quote(swap_path)}
FSTAB_PATH={shlex.quote(fstab_path)}
PROC_SWAPS_PATH={shlex.quote(proc_swaps_path)}
SWAP_BYTES=2147483648
swap_is_active() {{
  awk -v path="$SWAP_PATH" 'NR > 1 && $1 == path {{ found = 1 }} END {{ exit !found }}' \
    "$PROC_SWAPS_PATH"
}}
if sudo test -e "$SWAP_PATH" || sudo test -L "$SWAP_PATH"; then
  if ! sudo test -f "$SWAP_PATH" || sudo test -L "$SWAP_PATH"; then
    echo "Refusing to replace $SWAP_PATH: the existing path is not a regular file." >&2
    exit 1
  fi
  swap_type=$(sudo blkid -p -s TYPE -o value "$SWAP_PATH" 2>/dev/null || true)
  if [ "$swap_type" != swap ]; then
    echo "Refusing to replace $SWAP_PATH: the existing file has no swap signature." >&2
    exit 1
  fi
  swap_size=$(sudo stat -c %s "$SWAP_PATH")
  if [ "$swap_size" -lt "$SWAP_BYTES" ]; then
    if swap_is_active; then
      sudo swapoff "$SWAP_PATH"
    fi
    sudo fallocate -l 2G "$SWAP_PATH"
    sudo chmod 600 "$SWAP_PATH"
    sudo mkswap "$SWAP_PATH"
  fi
else
  sudo fallocate -l 2G "$SWAP_PATH"
  sudo chmod 600 "$SWAP_PATH"
  sudo mkswap "$SWAP_PATH"
fi
sudo chmod 600 "$SWAP_PATH"
swap_type=$(sudo blkid -p -s TYPE -o value "$SWAP_PATH" 2>/dev/null || true)
if [ "$swap_type" != swap ]; then
  echo "$SWAP_PATH does not have a valid swap signature after provisioning." >&2
  exit 1
fi
swap_size=$(sudo stat -c %s "$SWAP_PATH")
if [ "$swap_size" -lt "$SWAP_BYTES" ]; then
  echo "$SWAP_PATH is smaller than the required 2 GiB after provisioning." >&2
  exit 1
fi
if ! swap_is_active; then
  sudo swapon "$SWAP_PATH"
fi
active_size_kib=$(awk -v path="$SWAP_PATH" \
  'NR > 1 && $1 == path {{ print $3; exit }}' "$PROC_SWAPS_PATH")
page_size=$(getconf PAGESIZE)
minimum_active_kib=$(((SWAP_BYTES - page_size) / 1024))
if [ -z "$active_size_kib" ] || [ "$active_size_kib" -lt "$minimum_active_kib" ]; then
  echo "$SWAP_PATH is not active with the required 2 GiB capacity." >&2
  exit 1
fi
fstab_entries=$(sudo awk -v path="$SWAP_PATH" '$1 == path {{ count++ }} END {{ print count + 0 }}' \
  "$FSTAB_PATH")
if [ "$fstab_entries" -eq 0 ]; then
  printf '%s none swap sw 0 0\n' "$SWAP_PATH" | sudo tee -a "$FSTAB_PATH" >/dev/null
elif [ "$fstab_entries" -ne 1 ] || ! sudo awk -v path="$SWAP_PATH" \
  '$1 == path && $2 == "none" && $3 == "swap" && $4 == "sw" {{ valid++ }} \
   END {{ exit valid != 1 }}' "$FSTAB_PATH"; then
  echo "Refusing to alter ambiguous $SWAP_PATH entries in $FSTAB_PATH." >&2
  exit 1
fi
"""


def _host_prep_script() -> str:
    return f"""\
set -euo pipefail
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban
sudo systemctl disable --now rpcbind rpcbind.socket 2>/dev/null || true
# Re-asserting the image's own rules must never fail the pass: a host that
# rejects one of them is left as it is rather than half-reconfigured.
sudo iptables -C INPUT -i lo -j ACCEPT 2>/dev/null || \
  sudo iptables -I INPUT 3 -i lo -j ACCEPT || true
sudo iptables -C INPUT -j REJECT --reject-with icmp-host-prohibited 2>/dev/null || \
  sudo iptables -A INPUT -j REJECT --reject-with icmp-host-prohibited || true
sudo netfilter-persistent save 2>/dev/null || true
sudo install -d /etc/ssh/sshd_config.d
echo 'X11Forwarding no' | sudo tee /etc/ssh/sshd_config.d/echo-words.conf >/dev/null
sudo sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sshd -t
sudo systemctl reload ssh
sudo install -d /etc/fail2ban
sudo tee /etc/fail2ban/jail.local >/dev/null <<'ECHOWORDS_F2B_EOF'
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 100.64.0.0/10
bantime = 1d
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 30d
findtime = 10m
maxretry = 3

[sshd]
enabled = true
backend = systemd
ECHOWORDS_F2B_EOF
sudo install -d /etc/systemd/journald.conf.d
echo -e '[Journal]\nSystemMaxUse=200M' | sudo tee /etc/systemd/journald.conf.d/size.conf >/dev/null
sudo systemctl restart systemd-journald
{_swap_prep_script()}
sudo systemctl enable --now fail2ban
"""


@task(name="setup-app", help={"with_host_prep": "Apply the required VM2 hardening pass."})
def setup_app(c: Context, with_host_prep=False):
    """Prepare the production VM without changing or restarting a deployed revision."""
    if with_host_prep:
        _ssh(c, _host_prep_script())
    _ssh(
        c,
        "set -euo pipefail; "
        "sudo apt-get update; "
        "sudo apt-get install -y ca-certificates curl git python3 rsync; "
        "command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh; "
        "node_major=$(node -v 2>/dev/null | sed -e 's/^v//' -e 's/\\..*//' || true); "
        'if [ -z "$node_major" ] || [ "$node_major" -lt 22 ]; then '
        "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && "
        "sudo apt-get install -y nodejs; fi; node -v; npm -v; "
        f"test -d {REMOTE_ROOT}/.git || git clone {REPO_URL} {REMOTE_ROOT}; "
        f"cd {REMOTE_ROOT}; "
        "source /home/ubuntu/.local/bin/env; uv sync --no-dev; "
        f"install -d -m 700 {REMOTE_DATA}; "
        f"test -f {REMOTE_DATA}/languages.toml || "
        f"cp languages.example.toml {REMOTE_DATA}/languages.toml; "
        f"chmod 600 {REMOTE_DATA}/languages.toml; "
        "command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sudo sh",
    )
    _sync_deploy_env(c)
    _upload_service(c)
    _ssh(
        c,
        "sudo tailscale set --operator=ubuntu; "
        "tailscale serve --bg 8080; "
        f"sudo systemctl enable {SERVICE_NAME}",
    )


@task(help={"ref": "Git branch, tag, or commit to deploy (required)."})
def deploy(c: Context, ref=""):
    """Deploy an exact git ref, built on the server, and gate on liveness."""
    if not ref:
        raise RuntimeError("--ref is required, for example: inv deploy --ref=main")
    _deploy_host()
    if not DEPLOY_ENV.is_file():
        raise RuntimeError(f"Create {DEPLOY_ENV} from {DEPLOY_ENV_EXAMPLE} before deploying.")
    commit = _resolve_commit(c, ref)
    _ssh(c, _remote_deploy_script(commit))
    _sync_deploy_env(c)
    _upload_service(c)
    _ssh(c, f"sudo systemctl restart {SERVICE_NAME}")
    _health_check(c)


def _status_script() -> str:
    return (
        "set -euo pipefail; "
        f"sudo systemctl status {SERVICE_NAME} --no-pager; "
        "tailscale serve status; "
        f"systemctl show {SERVICE_NAME} -p MemoryCurrent -p MemoryHigh -p MemoryMax; "
        f"main_pid=$(systemctl show {SERVICE_NAME} --value -p MainPID); "
        "if [ \"$main_pid\" -gt 0 ] && [ -r \"/proc/$main_pid/status\" ]; then "
        "awk '$1 == \"VmRSS:\" { print \"ProcessVmRSSBytes=\" $2 * 1024 } "
        "$1 == \"VmHWM:\" { print \"ProcessVmHWMBytes=\" $2 * 1024 }' "
        "\"/proc/$main_pid/status\"; "
        "else echo ProcessVmRSSBytes=unavailable; echo ProcessVmHWMBytes=unavailable; fi; "
        f"control_group=$(systemctl show {SERVICE_NAME} --value -p ControlGroup); "
        "if [ -z \"$control_group\" ] || [ \"$control_group\" = / ]; then "
        "echo 'Service control group unavailable; refusing to read root memory.peak' >&2; "
        "exit 1; fi; "
        "peak_file=/sys/fs/cgroup${control_group}/memory.peak; "
        "if sudo test -r \"$peak_file\"; then printf 'CGroupMemoryPeak='; "
        "sudo cat \"$peak_file\"; else echo CGroupMemoryPeak=unsupported; fi; "
        "echo 'Recent dinary replica files:'; "
        "if sudo test -d /var/lib/litestream; then "
        "sudo find /var/lib/litestream -type f -printf '%TY-%Tm-%Td %TH:%TM %p\\n' "
        "| sort | tail -5; else echo 'Dinary replica tree unavailable'; fi"
    )


@task
def status(c: Context):
    """Show the production service, proxy, memory, and replica receive state."""
    _ssh(c, _status_script())


@task(help={"follow": "Follow new log lines.", "lines": "Number of existing lines."})
def logs(c: Context, follow=False, lines=100):
    """Show production service logs."""
    flag = "-f" if follow else f"-n {int(lines)} --no-pager"
    c.run(f"ssh {_deploy_host()} 'sudo journalctl -u {SERVICE_NAME} {flag}'")


def _ensure_languages_config():
    """Bootstrap the languages table so a fresh checkout can start the app."""
    target = Settings().languages_config.expanduser()
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(LANGUAGES_EXAMPLE, target)
    print(f"Created {target} from {LANGUAGES_EXAMPLE} — edit it to taste.")


@task(help={"port": "TCP port to listen on (default 8080).",
            "rebuild": "Rebuild _static/ from webapp/ before starting."})
def dev(c: Context, port=8080, rebuild=False):
    """Run the web app locally with uvicorn --reload (http://127.0.0.1:<port>).

    Serves the built bundle. For frontend work with hot reload run
    `npm --prefix webapp run dev` alongside it and open port 5173,
    which proxies /api here.
    """
    _ensure_languages_config()
    if rebuild or not (STATIC_PATH / "index.html").is_file():
        _run_build(c)
    c.run(
        f"uv run uvicorn echo_words.api:app --reload --reload-dir src "
        f"--host 127.0.0.1 --port {port}",
        pty=True,
    )


@task
def test(c: Context):
    """Run the Python suite and, when webapp/ is installed, the frontend one."""
    c.run("uv run pytest", pty=True)
    if (WEBAPP_PATH / "node_modules").is_dir():
        c.run(f"npm --prefix {WEBAPP_PATH} run test")
    else:
        print(f"Skipped the frontend tests: {WEBAPP_PATH}/node_modules is missing "
              f"(inv build-static installs it).")


namespace = Collection.from_module(sys.modules[__name__])
for name in ALLOWED_VERSION_TYPES:
    namespace.add_task(ver_task_factory(name), name=f"ver-{name}")  # type: ignore[bad-argument-type]
for name in ALLOWED_DOC_LANGUAGES:
    namespace.add_task(docs_task_factory(name), name=f"docs-{name}")  # type: ignore[bad-argument-type]
