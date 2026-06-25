"""Tests for hardened shell loading (backend-generated exports only)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ctx.cli import main
from ctx.storage import ensure_directories, set_config_dir, vault_file_path


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config directory and active vault env."""
    cfg = tmp_path / "config"
    set_config_dir(cfg / "ctx")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    ensure_directories()
    return cfg


def _write_raw_vault(name: str, text: str) -> Path:
    """Write raw vault contents, bypassing writer quoting."""
    path = vault_file_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_shell_load_emits_only_exports_and_unsets(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_shell load prints safe shell code for loading a vault."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    _write_raw_vault(
        "testvault",
        "export ip=10.10.10.1\nexport user='admin'\n",
    )

    assert main(["_shell", "load", "testvault"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert any(line.startswith("export ip=") for line in out)
    assert any(line.startswith("export user=") for line in out)
    # Must not emit arbitrary shell beyond export/unset.
    assert all(
        line.startswith("export ")
        or line.startswith("unset ")
        or line.startswith("CTX_LOADED_VAULT=")
        or line.startswith("export CTX_LOADED_VAULT=")
        for line in out
    )


def test_shell_load_quotes_metacharacters(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Metacharacters must be quoted so nothing is executed."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "weird")
    value = "spaces; $dollars `backticks` (parens) \"quotes\" 'single' \\slashes"
    _write_raw_vault(
        "weird",
        f"export token={value!s}\n",
    )

    assert main(["_shell", "load", "weird"]) == 0
    out = capsys.readouterr().out
    # Output must be a single assignment with robust quoting around the full value.
    assert "export token=" in out
    line = next(
        line_str
        for line_str in out.splitlines()
        if line_str.startswith("export token=")
    )
    rhs = line.split("=", 1)[1]
    # Must not allow unquoted command separators; `shlex.quote` yields a single-quoted
    # (or equivalent) string for unsafe characters.
    assert rhs.startswith("'") or rhs.startswith('"')
    assert (
        rhs.endswith("'") or rhs.endswith('"') or rhs.endswith("'\"'\"'")
    )  # shlex.quote embeds single quotes
    # The semicolon and other metacharacters are allowed only as data inside quotes.
    assert ";" in rhs
    assert "$dollars" in rhs


def test_shell_load_rejects_unsafe_variable_name(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unsafe variable names in vault content must be rejected clearly."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "bad")
    _write_raw_vault("bad", "export bad-key=1\n")

    assert main(["_shell", "load", "bad"]) == 1
    err = capsys.readouterr().err
    assert "unsafe" in err.lower() or "invalid" in err.lower()


def test_shell_load_rejects_malicious_non_assignment_line(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-assignment lines must not be executed; they should be rejected."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "pwn")
    _write_raw_vault(
        "pwn",
        "export ip=1.2.3.4\n$(touch /tmp/pwned)\nexport user=admin\n",
    )

    assert main(["_shell", "load", "pwn"]) == 1
    err = capsys.readouterr().err
    assert "line" in err.lower()


@pytest.mark.skipif(
    sys.platform == "win32", reason="Shell execution semantics are POSIX-specific"
)
def test_shell_output_is_valid_for_bash_and_zsh(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The emitted output should be portable to bash and zsh."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "portable")
    _write_raw_vault("portable", "export ip='10.0.0.1'\n")
    assert main(["_shell", "load", "portable"]) == 0
    out = capsys.readouterr().out
    # Basic sanity: no bashisms, just export/unset lines.
    assert "source " not in out
    assert ". " not in out


# ---------------------------------------------------------------------------
# Safe value handling via the public set path (round-trips through the writer)
# ---------------------------------------------------------------------------

SAFE_CASES = [
    ("ip", "10.10.10.10"),
    ("user", "admin"),
    ("password", "p@ss word"),
    ("token", "abc;def"),
    ("payload", "$(id)"),
    ("quoted", "hello ' world"),
    ("backtick", "`id`"),
    ("paren", "(test)"),
    ("dollar", "$HOME"),
]


@pytest.mark.parametrize("key,value", SAFE_CASES)
def test_shell_load_emits_quoted_safe_exports(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: str,
) -> None:
    """Safe single-line values are emitted as quoted, non-executing exports."""
    from ctx.storage import create_vault, set_variable

    monkeypatch.setenv("CTX_ACTIVE_VAULT", "safe")
    create_vault("safe")
    set_variable("safe", key, value)

    assert main(["_shell", "load", "safe"]) == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    # Only export/unset/CTX_LOADED_VAULT lines are ever emitted.
    assert all(
        line.startswith("export ")
        or line.startswith("unset ")
        or line.startswith("CTX_LOADED_VAULT=")
        for line in lines
    )
    export_line = next(line for line in lines if line.startswith(f"export {key}="))
    rhs = export_line.split("=", 1)[1]
    # Metacharacter-laden values must be quoted, never bare.
    if any(ch in value for ch in " ;$`()'\"&|"):
        assert rhs.startswith("'") or rhs.startswith('"')


@pytest.mark.parametrize(
    "raw",
    [
        "bad-key=value\n",
        "1bad=value\n",
        "KEY WITH SPACE=value\n",
        "$(touch /tmp/pwned)\n",
        "echo pwned\n",
        "malformed line without equals\n",
    ],
)
def test_shell_load_rejects_unsafe_or_malformed_lines(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    """Unsafe keys and executable-looking lines are rejected, not emitted."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "danger")
    _write_raw_vault("danger", raw)
    assert main(["_shell", "load", "danger"]) == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == ""  # nothing emitted for the shell to eval
    assert "error:" in captured.err.lower()


def test_shell_load_accepts_export_prefixed_line(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A normal 'export good=value' line is valid and accepted."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "ok")
    _write_raw_vault("ok", "export good=value\n")
    assert main(["_shell", "load", "ok"]) == 0
    out = capsys.readouterr().out
    assert any(line.startswith("export good=") for line in out.splitlines())


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="requires a POSIX bash to evaluate generated output",
)
def test_generated_exports_have_no_side_effects_when_evaluated(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Evaluating generated output in a real shell must not execute payloads."""
    from ctx.storage import create_vault, set_variable

    marker = tmp_path / "pwned_marker"
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "evaltest")
    create_vault("evaltest")
    # A value that *would* run a command if the output were unsafe.
    payload = f"$(touch {marker})"
    set_variable("evaltest", "payload", payload)

    assert main(["_shell", "load", "evaltest"]) == 0
    generated = capsys.readouterr().out

    # Evaluate the generated script in an isolated bash and echo the variable.
    result = subprocess.run(
        ["bash", "-c", f'{generated}\nprintf "%s" "$payload"'],
        capture_output=True,
        text=True,
        check=True,
    )
    assert not marker.exists()  # the command substitution never executed
    assert result.stdout == payload  # value preserved verbatim as data
