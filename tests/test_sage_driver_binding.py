r"""Contract tests for the tracked ``.envrc`` Sage-driver binding.

The sage QC profile runs the suite under ``$SAGE_BIN``'s interpreter; that
proof is only as strong as the binding, and the tracked ``.envrc`` is where
the binding is created.  Its contract: export ``SAGE_BIN`` only when the
value is a real SageMath driver, and otherwise exit nonzero so direnv
refuses to load an environment at all instead of exporting a weakened one.

Each test sources the actual ``.envrc`` under ``bash`` the way direnv does
(strict mode), with a stub ``$HOME`` so the machine-level ``~/.envrc`` it
sources first contributes nothing, and a controlled ``PATH``/``SAGE_BIN``.
"""

import os
import shutil
import subprocess
from pathlib import Path

ENVRC = Path(__file__).resolve().parent.parent / ".envrc"

# Resolved against the suite's own PATH: the stubbed child PATH is part of
# the scenario under test and must not decide whether bash itself exists.
_bash = shutil.which("bash")
assert _bash is not None
BASH: str = _bash

# The suite itself runs under the sage profile, so the validated driver is
# in the environment; a KeyError here is the same loud refusal the binding
# enforces.
REAL_SAGE = os.environ["SAGE_BIN"]


def _source_envrc(tmp_path: Path, *, path: str, sage_bin: str | None) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / ".envrc").write_text("")
    env = {"HOME": str(home), "PATH": path}
    if sage_bin is not None:
        env["SAGE_BIN"] = sage_bin
    return subprocess.run(
        [
            BASH,
            "-c",
            'set -euo pipefail; source "$1"; printf \'%s\\n\' "$SAGE_BIN"',
            "_",
            str(ENVRC),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_explicit_real_driver_is_accepted_and_exported(tmp_path: Path) -> None:
    result = _source_envrc(tmp_path, path=os.environ["PATH"], sage_bin=REAL_SAGE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == REAL_SAGE


def test_path_discovery_finds_and_validates_a_real_driver(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "sage").symlink_to(REAL_SAGE)
    result = _source_envrc(tmp_path, path=f"{bin_dir}:{os.environ['PATH']}", sage_bin=None)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(bin_dir / "sage")


def test_absent_driver_refuses_the_environment(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _source_envrc(tmp_path, path=str(empty), sage_bin=None)
    assert result.returncode != 0
    assert "SAGE_BIN" in result.stderr
    assert result.stdout == "", "a refused environment must export nothing"


def test_non_sage_executable_refuses_the_environment(tmp_path: Path) -> None:
    impostor = tmp_path / "sage"
    impostor.write_text("#!/bin/sh\necho not-sage\n")
    impostor.chmod(0o755)
    result = _source_envrc(tmp_path, path=os.environ["PATH"], sage_bin=str(impostor))
    assert result.returncode != 0
    assert "SageMath" in result.stderr
    assert result.stdout == "", "a refused environment must export nothing"
