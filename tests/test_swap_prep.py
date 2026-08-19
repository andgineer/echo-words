import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "swap_project_tasks",
    Path(__file__).parents[1] / "tasks.py",
)
assert _SPEC and _SPEC.loader
tasks = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tasks
_SPEC.loader.exec_module(tasks)


def _write_command(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\nset -eu\n{body}")
    path.chmod(0o755)


@pytest.fixture
def swap_script_harness(tmp_path):
    command_dir = tmp_path / "bin"
    command_dir.mkdir()
    call_log = tmp_path / "calls"
    proc_swaps = tmp_path / "proc-swaps"
    proc_swaps.write_text("Filename Type Size Used Priority\n")
    fstab = tmp_path / "fstab"
    fstab.write_text("# test fstab\n")
    swapfile = tmp_path / "swapfile"

    _write_command(command_dir / "sudo", 'exec "$@"\n')
    _write_command(
        command_dir / "fallocate",
        """\
test "$1" = -l
test "$2" = 2G
"$TEST_PYTHON" -c 'import sys; open(sys.argv[1], "wb").truncate(2147483648)' "$3"
printf 'fallocate\\n' >>"$FAKE_CALL_LOG"
""",
    )
    _write_command(
        command_dir / "stat",
        """\
test "$1" = -c
test "$2" = %s
"$TEST_PYTHON" -c 'import os, sys; print(os.path.getsize(sys.argv[1]))' "$3"
""",
    )
    _write_command(
        command_dir / "mkswap",
        """\
printf 'swap\\n' >"$1.swap-type"
printf 'mkswap\\n' >>"$FAKE_CALL_LOG"
""",
    )
    _write_command(
        command_dir / "blkid",
        """\
for path do :; done
test -f "$path.swap-type"
cat "$path.swap-type"
""",
    )
    _write_command(
        command_dir / "swapon",
        """\
if [ "${FAKE_SWAPON_FAIL:-0}" = 1 ]; then exit 42; fi
size_kib=${FAKE_ACTIVE_SIZE_KIB:-2097148}
printf '%s file %s 0 -2\\n' "$1" "$size_kib" >>"$FAKE_PROC_SWAPS"
printf 'swapon\\n' >>"$FAKE_CALL_LOG"
""",
    )
    _write_command(
        command_dir / "swapoff",
        """\
printf 'swapoff\\n' >>"$FAKE_CALL_LOG"
exit 99
""",
    )

    env = {
        **os.environ,
        "PATH": f"{command_dir}:{os.environ['PATH']}",
        "TEST_PYTHON": sys.executable,
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_PROC_SWAPS": str(proc_swaps),
    }
    script = "set -euo pipefail\n" + tasks._swap_prep_script(  # noqa: SLF001
        str(swapfile),
        str(fstab),
        str(proc_swaps),
    )

    def run(**extra_env):
        return subprocess.run(  # noqa: S603 - fixed local script under a fake PATH.
            ["bash", "-c", script],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
            env={**env, **extra_env},
        )

    return run, swapfile, fstab, proc_swaps, call_log


def test_swap_prep_creates_activates_and_persists_swap_idempotently(swap_script_harness):
    run, swapfile, fstab, _proc_swaps, call_log = swap_script_harness

    first = run()
    second = run()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert swapfile.stat().st_size == 2147483648
    assert fstab.read_text().splitlines().count(f"{swapfile} none swap sw 0 0") == 1
    assert call_log.read_text().splitlines() == ["fallocate", "mkswap", "swapon"]


def test_swap_prep_refuses_to_overwrite_an_existing_non_swap_file(swap_script_harness):
    run, swapfile, fstab, _proc_swaps, call_log = swap_script_harness
    swapfile.write_bytes(b"not swap")
    os.truncate(swapfile, 2147483648)

    result = run()

    assert result.returncode != 0
    assert "existing file has no swap signature" in result.stderr
    assert swapfile.read_bytes()[:8] == b"not swap"
    assert fstab.read_text() == "# test fstab\n"
    assert not call_log.exists()


def test_swap_prep_treats_swapon_failure_as_fatal(swap_script_harness):
    run, _swapfile, fstab, _proc_swaps, _call_log = swap_script_harness

    result = run(FAKE_SWAPON_FAIL="1")

    assert result.returncode == 42
    assert fstab.read_text() == "# test fstab\n"


def test_swap_prep_rejects_an_active_swap_smaller_than_two_gib(swap_script_harness):
    run, _swapfile, fstab, _proc_swaps, _call_log = swap_script_harness

    result = run(FAKE_ACTIVE_SIZE_KIB="1048572")

    assert result.returncode != 0
    assert "not active with the required 2 GiB capacity" in result.stderr
    assert fstab.read_text() == "# test fstab\n"
