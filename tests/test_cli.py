"""Tests for the ctxctl CLI."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from ctx.cli import main
from ctx.storage import ensure_vault, set_config_dir, vault_file_path


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config directory and provide active vault env."""
    cfg = tmp_path / "config" / "ctx"
    set_config_dir(cfg)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    ensure_vault("testvault")
    return cfg


def run_cli(args: List[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """Run main() with given args and capture exit code."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    return main(args)


def test_help_exits_zero() -> None:
    """--help returns success."""
    assert main(["--help"]) == 0


def test_set_get_show(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """set and get commands work with active vault."""
    assert run_cli(["set", "ip", "10.10.10.1"], monkeypatch) == 0
    assert run_cli(["get", "ip"], monkeypatch) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "10.10.10.1"

    assert run_cli(["show"], monkeypatch) == 0
    show_out = capsys.readouterr().out
    assert "testvault" in show_out
    assert "10.10.10.1" in show_out


def test_set_with_spaces(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """set preserves values containing spaces."""
    assert run_cli(["set", "desc", "hello", "world"], monkeypatch) == 0
    assert run_cli(["get", "desc"], monkeypatch) == 0
    assert capsys.readouterr().out.strip() == "hello world"


def test_current_without_active_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """current fails when CTX_ACTIVE_VAULT is unset."""
    monkeypatch.delenv("CTX_ACTIVE_VAULT", raising=False)
    assert main(["current"]) == 1


def test_set_without_active_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """set fails when no active vault is set."""
    monkeypatch.delenv("CTX_ACTIVE_VAULT", raising=False)
    assert main(["set", "ip", "1.2.3.4"]) == 1


def test_invalid_key_rejected(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid key names are rejected."""
    assert run_cli(["set", "bad-key", "value"], monkeypatch) == 1


def test_list_vaults(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """list shows existing vaults."""
    ensure_vault("another")
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "testvault" in out
    assert "another" in out


def test_path_command(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """path prints the active vault file path."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    assert main(["path"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("testvault.env")


def test_clear_force(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """clear --force removes all variables."""
    run_cli(["set", "ip", "1.2.3.4"], monkeypatch)
    assert run_cli(["clear", "--force"], monkeypatch) == 0
    path = vault_file_path("testvault")
    assert path.read_text(encoding="utf-8") == ""


def test_delete_force(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """delete --force removes a vault."""
    ensure_vault("gone")
    assert main(["delete", "gone", "--force"]) == 0
    assert not vault_file_path("gone").exists()


def test_rename_command(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rename changes vault name on disk."""
    ensure_vault("oldone")
    run_cli(["set", "ip", "1.1.1.1"], monkeypatch)
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "oldone")
    assert main(["rename", "oldone", "newone"]) == 0
    assert not vault_file_path("oldone").exists()
    assert vault_file_path("newone").exists()


def test_duplicate_command(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """duplicate copies vault contents."""
    from ctx.storage import get_variable, set_variable

    ensure_vault("src")
    set_variable("src", "ip", "9.9.9.9")
    assert main(["duplicate", "src", "dst"]) == 0
    assert get_variable("dst", "ip") == "9.9.9.9"


def test_validation_warning_on_set(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Validation warnings go to stderr but do not fail the command."""
    code = run_cli(["set", "ip", "not-valid"], monkeypatch)
    assert code == 0
    err = capsys.readouterr().err
    assert "warning:" in err


def test_shell_path(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_shell path prints vault path for shell load."""
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "testvault")
    assert main(["_shell", "path"]) == 0
    assert "testvault.env" in capsys.readouterr().out


def test_shell_keys(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_shell keys lists keys for completions."""
    run_cli(["set", "ip", "1.2.3.4"], monkeypatch)
    run_cli(["set", "user", "admin"], monkeypatch)
    assert main(["_shell", "keys"]) == 0
    out = capsys.readouterr().out
    assert "ip" in out
    assert "user" in out


def test_shell_keys_for(config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """_shell keys-for lists keys for any vault without active vault env."""
    from ctx.storage import create_vault, set_variable

    create_vault("othervault")
    set_variable("othervault", "ip", "10.0.0.1")
    assert main(["_shell", "keys-for", "othervault"]) == 0
    out = capsys.readouterr().out
    assert "ip" in out


def test_create_vault(config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """create makes a new vault file."""
    assert main(["create", "newvault"]) == 0
    assert vault_file_path("newvault").exists()
    assert "Created vault" in capsys.readouterr().out


def test_create_duplicate_fails(config_dir: Path) -> None:
    """create fails if vault already exists."""
    ensure_vault("exists")
    assert main(["create", "exists"]) == 1


def test_load_missing_vault_fails(
    config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """load fails when vault does not exist and suggests create."""
    code = main(["load", "frest"])
    assert code == 1
    err = capsys.readouterr().err
    assert "does not exist" in err
    assert "ctx create frest" in err
    assert not vault_file_path("frest").exists()


def test_load_existing_vault(config_dir: Path) -> None:
    """load succeeds when vault exists."""
    ensure_vault("forest")
    assert main(["load", "forest"]) == 0


def test_load_reload_active_vault(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load without vault name validates active vault exists."""
    ensure_vault("active")
    monkeypatch.setenv("CTX_ACTIVE_VAULT", "active")
    assert main(["load"]) == 0
