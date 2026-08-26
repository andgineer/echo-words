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
    assert "/etc/systemd/journald.conf.d/echo-words.conf" in script
    assert "SystemMaxUse=200M" in script
    assert "MaxRetentionSec=3month" in script


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


def test_resolve_commit_pins_the_ref_without_reading_the_local_checkout():
    commit = "a" * 40
    context = _Context([f"{commit}\n"])

    assert tasks._resolve_commit(context, "v0.1.0") == commit
    assert context.commands == ["git rev-parse --verify --end-of-options 'v0.1.0^{commit}'"]


def test_resolve_commit_deploys_a_ref_the_working_tree_is_neither_on_nor_clean_for():
    """Nothing local reaches the server, so a dirty tree on another branch is deployable."""
    commit = "a" * 40
    context = _Context([f"{commit}\n"])

    assert tasks._resolve_commit(context, "v0.1.0") == commit
    assert not any("git status" in command for command in context.commands)
    assert not any("rev-parse --verify HEAD" in command for command in context.commands)


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
    static = tmp_path / "_static"
    static.mkdir()
    (static / "index.html").write_text("server-side build output")
    node_modules = tmp_path / "webapp" / "node_modules"
    node_modules.mkdir(parents=True)
    (node_modules / ".package-lock.json").write_text("npm ci output")
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


def test_deploy_builds_the_checked_out_commit_on_the_server(monkeypatch, tmp_path):
    commit = "a" * 40
    remote_scripts = []
    context = _Context([f"{commit}\n"])
    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10\n")

    monkeypatch.setattr(
        tasks,
        "_run_build",
        lambda _context: pytest.fail("deploy must not build the frontend locally"),
    )
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_sync_deploy_env", lambda _context: None)
    monkeypatch.setattr(tasks, "_upload_service", lambda _context: None)
    monkeypatch.setattr(tasks, "_health_check", lambda _context: None)
    monkeypatch.setattr(tasks, "_deploy_host", lambda: "echo-words")

    tasks.deploy.body(context, ref="main")

    checkout = remote_scripts[0]
    dirty_check = "git status --porcelain --untracked-files=normal"
    assert checkout.count(dirty_check) == 2
    assert checkout.index(dirty_check) < checkout.index(f"git fetch origin {commit}")
    assert checkout.index(f"git checkout --detach {commit}") < checkout.rindex(dirty_check)
    assert checkout.rindex(dirty_check) < checkout.index("uv sync --no-dev")
    assert checkout.index("uv sync --no-dev") < checkout.index("uv run --no-dev inv build-static")
    assert f'test "$(git rev-parse HEAD)" = {commit}' in checkout
    assert "git clean" not in checkout
    assert "git reset" not in checkout
    assert context.commands == ["git rev-parse --verify --end-of-options 'main^{commit}'"]


def test_remote_deploy_fails_closed_without_deleting_data_or_secrets():
    script = tasks._remote_deploy_script("a" * 40)

    assert "Refusing to deploy over remote working-tree changes" in script
    assert "--untracked-files=normal" in script
    assert "rm " not in script
    assert "git clean" not in script
    assert f"{tasks.REMOTE_ROOT}/.deploy" not in script


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


def test_deploy_checks_the_local_secrets_before_touching_the_server(monkeypatch):
    """A missing .deploy/.env must fail before any remote command runs."""
    remote_scripts = []
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_resolve_commit", lambda _context, _ref: "a" * 40)

    with pytest.raises(RuntimeError, match="Copy"):
        tasks.deploy.body(_Context([]), ref="main")

    assert remote_scripts == []


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
    assert "deb.nodesource.com/setup_22.x" in script
    assert "git clone" in script
    assert "git fetch origin main" not in script
    assert "git checkout" not in script
    assert "systemctl enable echo-words" in script
    assert "systemctl enable --now echo-words" not in script
    assert "systemctl restart echo-words" not in script


def test_setup_installs_the_node_toolchain_the_server_side_build_needs(monkeypatch):
    remote_scripts = []
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_sync_deploy_env", lambda _context: None)
    monkeypatch.setattr(tasks, "_upload_service", lambda _context: None)

    tasks.setup_app.body(_Context([]))

    script = " ".join(remote_scripts)
    assert "node_major=$(node -v 2>/dev/null" in script
    assert "|| true)" in script
    assert 'if [ -z "$node_major" ] || [ "$node_major" -lt 22 ]' in script
    assert "sudo apt-get install -y nodejs" in script
    assert script.index("node_major=") < script.index("git clone")


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


def _rebuild_context(monkeypatch, tmp_path, answer: str):
    remote_scripts = []
    _write_deploy_env(monkeypatch, tmp_path, "ECHOWORDS_DEPLOY_HOST=ubuntu@203.0.113.10\n")
    monkeypatch.setattr(tasks, "_ssh", lambda _context, script: remote_scripts.append(script))
    monkeypatch.setattr(tasks, "_health_check", lambda _context: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": answer)
    return remote_scripts


@pytest.mark.parametrize("answer", ["", "no", "y", "YES", " yes please "])
def test_rebuild_note_type_deletes_nothing_without_a_typed_confirmation(
    monkeypatch,
    tmp_path,
    answer,
):
    remote_scripts = _rebuild_context(monkeypatch, tmp_path, answer)

    tasks.rebuild_note_type.body(_Context([]))

    assert not any("--yes" in script for script in remote_scripts)
    assert remote_scripts[-1] == "sudo systemctl start echo-words"


def test_rebuild_note_type_runs_the_cli_under_the_data_dir_the_service_uses():
    """The CLI reads the data dir from the environment alone. Pointed anywhere else it
    would find no collection, and report having nothing to rebuild while production
    stays broken. The value is passed in, never sourced: the deploy env sits next to
    an AnkiWeb password, and a shell would run whatever that password contains."""
    for confirmed in (False, True):
        script = tasks._rebuild_note_type_script(
            confirmed=confirmed,
            data_dir="/home/ubuntu/echo-words/data",
        )
        assert "ECHOWORDS_DATA_DIR=/home/ubuntu/echo-words/data uv run " in script
        assert tasks.REMOTE_DEPLOY_ENV not in script
        assert script.index("ECHOWORDS_DATA_DIR") < script.index("echo-words rebuild-note-type")
        assert script.index("systemctl stop echo-words") < script.index("ECHOWORDS_DATA_DIR")
        assert script.endswith("--yes") is confirmed


def test_a_data_dir_carrying_shell_syntax_reaches_the_vm_as_one_literal_value():
    script = tasks._rebuild_note_type_script(
        confirmed=True,
        data_dir="/home/ubuntu/$(touch pwned) data",
    )

    assert "ECHOWORDS_DATA_DIR='/home/ubuntu/$(touch pwned) data' uv run " in script


def test_a_deploy_env_naming_no_data_dir_leaves_the_cli_on_the_service_default():
    """An empty assignment would be a data dir of "", which is not the default the
    service falls back to."""
    script = tasks._rebuild_note_type_script(confirmed=True, data_dir="")

    assert "ECHOWORDS_DATA_DIR" not in script


def test_the_data_dir_is_parsed_rather_than_sourced(monkeypatch, tmp_path):
    """Read the way systemd reads an EnvironmentFile, not the way a shell would. A
    shell takes the quote inside the password as opening a string, closes it on the
    quote two lines down, and leaves the data dir unset without ever failing."""
    _write_deploy_env(
        monkeypatch,
        tmp_path,
        'ECHOWORDS_ANKIWEB_PASSWORD=pa"ss\n'
        "ECHOWORDS_DATA_DIR=/home/ubuntu/echo-words/data\n"
        'ECHOWORDS_TARGET_LANG=ru"\n',
    )

    assert tasks._remote_data_dir() == "/home/ubuntu/echo-words/data"


def test_rebuild_note_type_counts_before_it_deletes(monkeypatch, tmp_path):
    remote_scripts = _rebuild_context(monkeypatch, tmp_path, "yes")

    tasks.rebuild_note_type.body(_Context([]))

    counted, deleted = remote_scripts[0], remote_scripts[1]
    assert "--yes" not in counted
    assert deleted.endswith("--yes")
    assert remote_scripts[-1] == "sudo systemctl start echo-words"


def test_rebuild_note_type_restarts_the_service_when_the_delete_fails(monkeypatch, tmp_path):
    """The confirmation sits between the stop and the start: no path may leave it down."""
    remote_scripts = _rebuild_context(monkeypatch, tmp_path, "yes")

    def fail_the_delete(_context, script):
        remote_scripts.append(script)
        if "--yes" in script:
            raise RuntimeError("remote command exited 1")

    monkeypatch.setattr(tasks, "_ssh", fail_the_delete)

    with pytest.raises(RuntimeError):
        tasks.rebuild_note_type.body(_Context([]))

    assert remote_scripts[-1] == "sudo systemctl start echo-words"


def test_rebuild_note_type_restarts_the_service_when_the_operator_interrupts(monkeypatch, tmp_path):
    remote_scripts = _rebuild_context(monkeypatch, tmp_path, "yes")

    def interrupt(_prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)

    with pytest.raises(KeyboardInterrupt):
        tasks.rebuild_note_type.body(_Context([]))

    assert remote_scripts[-1] == "sudo systemctl start echo-words"
