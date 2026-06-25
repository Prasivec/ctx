"""End-to-end bash shell-integration tests.

These exercise the real `ctx` shell function from ``shell/ctx.sh`` against the
Python backend in a fully isolated HOME/XDG_CONFIG_HOME. They are skipped on
Windows and anywhere bash is unavailable; CI (Linux) runs them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_SH = REPO_ROOT / "shell" / "ctx.sh"
SRC_DIR = REPO_ROOT / "src"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="requires POSIX bash",
)


def _env(home: Path) -> dict[str, str]:
    """Build an isolated environment with a ctxctl wrapper on disk."""
    bindir = home / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    wrapper = bindir / "ctxctl"
    wrapper.write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" -m ctx "$@"\n',
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o755)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing if existing else "")
    env["CTXCTL_BIN"] = str(wrapper)
    for var in ("CTX_ACTIVE_VAULT", "CTX_LOADED_VAULT", "CTX_LOADED_KEYS"):
        env.pop(var, None)
    return env


def _run(home: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Source the bash integration and run a scenario body in one shell."""
    script = f'set -u\nsource "{SHELL_SH}"\n{body}\n'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=_env(home),
    )


def test_e2e_unset_clears_shell_variable(tmp_path: Path) -> None:
    """ctx unset removes the variable from the live shell."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create a >/dev/null",
                "ctx load a >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                'printf "BEFORE=[%s]\\n" "${ip-}"',
                "ctx unset ip >/dev/null",
                'printf "AFTER=[%s]\\n" "${ip-}"',
            ]
        ),
    )
    assert "BEFORE=[1.1.1.1]" in res.stdout, res
    assert "AFTER=[]" in res.stdout, res


def test_e2e_clear_clears_all_shell_variables(tmp_path: Path) -> None:
    """ctx clear --force removes all loaded variables from the live shell."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create a >/dev/null",
                "ctx load a >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                "ctx set user admin >/dev/null",
                'printf "BEFORE=[%s:%s]\\n" "${ip-}" "${user-}"',
                "ctx clear --force >/dev/null",
                'printf "AFTER=[%s:%s]\\n" "${ip-}" "${user-}"',
            ]
        ),
    )
    assert "BEFORE=[1.1.1.1:admin]" in res.stdout, res
    assert "AFTER=[:]" in res.stdout, res


def test_e2e_same_vault_reload_clears_removed_key(tmp_path: Path) -> None:
    """Reloading the same vault drops a key removed behind the shell's back."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create a >/dev/null",
                "ctx load a >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                # Remove the key via the backend directly (no shell refresh).
                '"$CTXCTL_BIN" unset ip >/dev/null',
                'printf "STALE=[%s]\\n" "${ip-}"',
                "ctx load a >/dev/null",
                'printf "AFTER=[%s]\\n" "${ip-}"',
            ]
        ),
    )
    assert "STALE=[1.1.1.1]" in res.stdout, res
    assert "AFTER=[]" in res.stdout, res


def test_e2e_vault_switching(tmp_path: Path) -> None:
    """Switching between vaults swaps variables correctly."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create a >/dev/null",
                "ctx load a >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                "ctx create b >/dev/null",
                "ctx load b >/dev/null",
                "ctx set ip 2.2.2.2 >/dev/null",
                'printf "B=[%s]\\n" "${ip-}"',
                "ctx load a >/dev/null",
                'printf "A=[%s]\\n" "${ip-}"',
            ]
        ),
    )
    assert "B=[2.2.2.2]" in res.stdout, res
    assert "A=[1.1.1.1]" in res.stdout, res


def test_e2e_failed_load_rolls_back(tmp_path: Path) -> None:
    """A malformed target leaves the previous vault and variables intact."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create good >/dev/null",
                "ctx load good >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                "ctx create bad >/dev/null",
                "printf '%s\\n' 'bad-key=value' "
                '> "$XDG_CONFIG_HOME/ctx/vaults/bad.env"',
                "ctx load bad >/dev/null 2>&1 || true",
                'printf "STATE=[%s:%s:%s]\\n" '
                '"${CTX_ACTIVE_VAULT-}" "${CTX_LOADED_VAULT-}" "${ip-}"',
            ]
        ),
    )
    assert "STATE=[good:good:1.1.1.1]" in res.stdout, res


def test_e2e_unload_clears_state(tmp_path: Path) -> None:
    """ctx unload removes variables and clears active/loaded state."""
    res = _run(
        tmp_path,
        "\n".join(
            [
                "ctx create a >/dev/null",
                "ctx load a >/dev/null",
                "ctx set ip 1.1.1.1 >/dev/null",
                "ctx unload >/dev/null",
                'printf "STATE=[%s:%s:%s]\\n" '
                '"${ip-}" "${CTX_ACTIVE_VAULT-}" "${CTX_LOADED_VAULT-}"',
            ]
        ),
    )
    assert "STATE=[::]" in res.stdout, res
