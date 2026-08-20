import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "project_tasks",
    Path(__file__).parents[1] / "tasks.py",
)
assert _SPEC and _SPEC.loader
tasks = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tasks
_SPEC.loader.exec_module(tasks)


@pytest.fixture(autouse=True)
def _never_read_the_operator_own_deploy_env(monkeypatch, tmp_path):
    """A developer machine has .deploy/.env and CI does not: pin every test to neither."""
    monkeypatch.delenv("ECHOWORDS_DEPLOY_HOST", raising=False)
    monkeypatch.setattr(tasks, "DEPLOY_ENV", tmp_path / "unset" / ".env")


def test_systemd_unit_has_the_required_network_gate_and_sandbox():
    unit = tasks.SYSTEMD_UNIT

    assert "After=network-online.target tailscaled.service" in unit
    assert "ExecStartPre=" in unit
    assert "tailscale ip -4" in unit
    assert "EnvironmentFile=/home/ubuntu/echo-words/.deploy/.env" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/home/ubuntu/echo-words/data" in unit
    assert "MemoryHigh=400M" in unit
    assert "MemoryMax=500M" in unit


def test_host_prep_provisions_swap_hardening_and_bounded_journal():
    script = tasks._host_prep_script()

    assert 'sudo fallocate -l 2G "$SWAP_PATH"' in script
    assert 'sudo swapon "$SWAP_PATH"' in script
    assert "minimum_active_kib=" in script
    assert "|| true\nsudo swapon" not in script
    assert "disable --now rpcbind rpcbind.socket" in script
    assert "PermitRootLogin no" in script
    assert "fail2ban" in script
    assert "SystemMaxUse=200M" in script


def test_host_prep_never_fails_on_the_firewall_recheck():
    script = tasks._host_prep_script()

    assert "sudo iptables -I INPUT 3 -i lo -j ACCEPT || true" in script
    assert "sudo iptables -A INPUT -j REJECT --reject-with icmp-host-prohibited || true" in script
    assert "sudo netfilter-persistent save 2>/dev/null || true" in script
    assert "iptables-persistent" not in script


def test_host_prep_enables_an_explicit_systemd_sshd_jail_without_banning_tailnet_admins():
    script = tasks._host_prep_script()

    assert "/etc/fail2ban/jail.local" in script
    assert "[sshd]" in script
    assert "enabled = true" in script
    assert "backend = systemd" in script
    assert "ignoreip = 127.0.0.1/8 ::1 100.64.0.0/10" in script
    assert "bantime = 1d" in script
    assert "bantime.increment = true" in script
    assert "bantime.factor = 2" in script
    assert "bantime.maxtime = 30d" in script
    assert "findtime = 10m" in script
    assert "maxretry = 3" in script
    assert script.index("/etc/fail2ban/jail.local") < script.index(
        "systemctl enable --now fail2ban",
    )


def test_example_env_documents_freetier_and_paid_provider_keys():
    example = (Path(__file__).parents[1] / ".deploy.example" / ".env").read_text()

    for key in (
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "ZAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        assert f"{key}=" in example


class _Result:
    def __init__(self, stdout=""):
        self.stdout = stdout


class _Context:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.commands = []

    def run(self, command, **_kwargs):
        self.commands.append(command)
        return _Result(next(self.outputs))


def test_deploy_commit_accepts_only_a_clean_matching_checkout():
    commit = "a" * 40
    context = _Context(["", f"{commit}\n", f"{commit}\n"])

    assert tasks._deploy_commit(context, "v0.1.0") == commit
    assert context.commands == [
        "git status --porcelain --untracked-files=normal",
        "git rev-parse --verify --end-of-options 'v0.1.0^{commit}'",
        "git rev-parse --verify HEAD",
    ]


def test_deploy_commit_rejects_dirty_source_before_resolving_ref():
    context = _Context([" M webapp/src/App.vue\n"])

    with pytest.raises(RuntimeError, match="dirty working tree"):
        tasks._deploy_commit(context, "main")

    assert context.commands == ["git status --porcelain --untracked-files=normal"]


def test_deploy_commit_rejects_ref_that_does_not_match_frontend_source():
    target = "a" * 40
    head = "b" * 40
    context = _Context(["", f"{target}\n", f"{head}\n"])

    with pytest.raises(RuntimeError, match="frontend source"):
        tasks._deploy_commit(context, "main")


def test_setup_runtime_data_is_the_only_root_data_ignored_by_deploy_guard(tmp_path):
    root = Path(__file__).parents[1]
    (tmp_path / ".gitignore").write_text((root / ".gitignore").read_text())
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=echo-words tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
    )

    runtime_data = tmp_path / "data"
    runtime_data.mkdir(mode=0o700)
    (runtime_data / "languages.toml").write_text("runtime configuration")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("setup-created environment")
    (tmp_path / ".deploy").mkdir()
    (tmp_path / ".deploy" / ".env").write_text("setup-synced secrets")
    clean = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert clean.stdout == ""

    nested_data = tmp_path / "fixtures" / "data"
    nested_data.mkdir(parents=True)
    (nested_data / "unexpected.toml").write_text("must not be hidden")
    (tmp_path / "unexpected.txt").write_text("must not be hidden")
    unexpected = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert unexpected.stdout == "?? fixtures/\n?? unexpected.txt\n"


def test_deploy_checks_out_the_same_commit_used_for_the_local_build(monkeypatch, tmp_path):
    commit = "a" * 40
    remote_scripts = []
    context = _Context([""])
    deploy_commits = []
    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10\n")

    def check_commit(_context, _ref):
        deploy_commits.append(commit)
        return commit

    monkeypatch.setattr(tasks, "_deploy_commit", check_commit)
    monkeypatch.setattr(tasks, "_run_build", lambda _context: None)
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_sync_deploy_env", lambda _context: None)
    monkeypatch.setattr(tasks, "_upload_service", lambda _context: None)
    monkeypatch.setattr(tasks, "_health_check", lambda _context: None)
    monkeypatch.setattr(tasks, "_deploy_host", lambda: "echo-words")

    tasks.deploy.body(context, ref="main")

    assert deploy_commits == [commit, commit]
    checkout = remote_scripts[0]
    dirty_check = "git status --porcelain --untracked-files=normal"
    assert checkout.count(dirty_check) == 2
    assert checkout.index(dirty_check) < checkout.index(f"git fetch origin {commit}")
    assert checkout.index(f"git checkout --detach {commit}") < checkout.rindex(dirty_check)
    assert checkout.rindex(dirty_check) < checkout.index("uv sync --no-dev")
    assert f'test "$(git rev-parse HEAD)" = {commit}' in checkout
    assert "git clean" not in checkout
    assert "git reset" not in checkout
    assert context.commands == [
        "rsync -az --delete _static/ echo-words:/home/ubuntu/echo-words/_static/",
    ]


def test_remote_deploy_fails_closed_without_deleting_data_or_secrets():
    script = tasks._remote_deploy_script("a" * 40)

    assert "Refusing to deploy over remote working-tree changes" in script
    assert "--untracked-files=normal" in script
    assert "rm " not in script
    assert "git clean" not in script
    assert f"{tasks.REMOTE_ROOT}/.deploy" not in script


def test_deploy_stops_if_source_changes_during_the_frontend_build(monkeypatch, tmp_path):
    before = "a" * 40
    after = "b" * 40
    context = _Context([])
    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10\n")
    monkeypatch.setattr(tasks, "_deploy_commit", lambda _context, _ref: checkouts.pop(0))
    monkeypatch.setattr(tasks, "_run_build", lambda _context: None)
    checkouts = [before, after]

    with pytest.raises(RuntimeError, match="changed during the frontend build"):
        tasks.deploy.body(context, ref="main")


def _write_deploy_env(monkeypatch, tmp_path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    monkeypatch.setattr(tasks, "DEPLOY_ENV", env_file)
    return env_file


def test_deploy_host_comes_from_the_deploy_env_file(monkeypatch, tmp_path):
    _write_deploy_env(
        monkeypatch,
        tmp_path,
        "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10 # VM2\n",
    )

    assert tasks._deploy_host() == "ubuntu@203.0.113.10"


def test_deploy_host_env_var_overrides_the_file(monkeypatch, tmp_path):
    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10\n")
    monkeypatch.setenv("ECHOWORDS_DEPLOY_HOST", "ubuntu@198.51.100.7")

    assert tasks._deploy_host() == "ubuntu@198.51.100.7"


def test_deploy_host_rejects_a_missing_file_and_an_unedited_placeholder(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="Copy"):
        tasks._deploy_host()

    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@<PUBLIC_IP>\n")
    with pytest.raises(RuntimeError, match="ssh destination"):
        tasks._deploy_host()


def test_deploy_resolves_the_target_before_the_frontend_build(monkeypatch):
    """A missing target must not cost a full frontend build first."""
    builds = []
    monkeypatch.setattr(tasks, "_run_build", lambda _context: builds.append(True))
    monkeypatch.setattr(tasks, "_deploy_commit", lambda _context, _ref: "a" * 40)

    with pytest.raises(RuntimeError, match="Copy"):
        tasks.deploy.body(_Context([]), ref="main")

    assert builds == []


def test_setup_does_not_move_or_restart_an_existing_deployment(monkeypatch):
    remote_scripts = []
    context = _Context([])
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_sync_deploy_env", lambda _context: None)
    monkeypatch.setattr(tasks, "_upload_service", lambda _context: None)
    monkeypatch.setattr(
        tasks,
        "_health_check",
        lambda _context: pytest.fail("setup must not start or health-check the service"),
    )

    tasks.setup_app.body(context)

    script = " ".join(remote_scripts)
    assert "git clone" in script
    assert "git fetch origin main" not in script
    assert "git checkout" not in script
    assert "systemctl enable echo-words" in script
    assert "systemctl enable --now echo-words" not in script
    assert "systemctl restart echo-words" not in script


def test_status_separates_process_and_cgroup_memory_measurements():
    script = tasks._status_script()

    assert script.startswith("set -euo pipefail;")
    assert "-p MemoryCurrent -p MemoryHigh -p MemoryMax" in script
    assert "-p MemoryPeak" not in script
    assert "ProcessVmRSSBytes=" in script
    assert "ProcessVmHWMBytes=" in script
    assert "VmRSS:" in script
    assert "VmHWM:" in script
    assert "--value -p ControlGroup" in script
    guard = 'if [ -z "$control_group" ] || [ "$control_group" = / ]'
    assert guard in script
    assert script.index(guard) < script.index(
        "peak_file=/sys/fs/cgroup${control_group}/memory.peak",
    )
    assert "/sys/fs/cgroup${control_group}/memory.peak" in script
    assert "CGroupMemoryPeak=" in script
    assert "CGroupMemoryPeak=unsupported" in script
    assert "else main_pid=" not in script
    assert "tail -5 || true" not in script
