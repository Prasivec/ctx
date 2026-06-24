"""Tests for vault storage, parsing, and permissions."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from ctx.errors import KeyNotFoundError, VaultExistsError, VaultNotFoundError
from ctx.storage import (
    clear_vault,
    create_vault,
    delete_vault,
    duplicate_vault,
    ensure_directories,
    ensure_vault,
    get_variable,
    list_vaults,
    parse_shell_value,
    read_vault,
    rename_vault,
    set_config_dir,
    set_variable,
    unset_variable,
    vault_file_path,
    write_vault,
)


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config directory for each test."""
    cfg = tmp_path / "config" / "ctx"
    set_config_dir(cfg)
    monkeypatch.setenv("HOME", str(tmp_path))
    return cfg


def test_ensure_vault_creates_file(config_dir: Path) -> None:
    """ensure_vault creates an empty vault file."""
    path = ensure_vault("forest")
    assert path.exists()
    assert path.name == "forest.env"
    assert read_vault(path) == {}


def test_create_vault(config_dir: Path) -> None:
    """create_vault creates a new vault and rejects duplicates."""
    path = create_vault("newone")
    assert path.exists()
    with pytest.raises(VaultExistsError):
        create_vault("newone")


def test_set_requires_existing_vault(config_dir: Path) -> None:
    """set_variable does not create vaults implicitly."""
    with pytest.raises(VaultNotFoundError):
        set_variable("missing", "ip", "1.2.3.4")
def test_set_get_unset(config_dir: Path) -> None:
    """Variables can be set, retrieved, and removed."""
    ensure_vault("lab")
    set_variable("lab", "ip", "10.10.10.1")
    assert get_variable("lab", "ip") == "10.10.10.1"
    unset_variable("lab", "ip")
    with pytest.raises(KeyNotFoundError):
        get_variable("lab", "ip")


def test_safe_quoting_special_characters(config_dir: Path) -> None:
    """Special characters and spaces are preserved via shell quoting."""
    ensure_vault("secrets")
    value = "Password123! $pecial \"chars\""
    set_variable("secrets", "pass", value)
    path = vault_file_path("secrets")
    content = path.read_text(encoding="utf-8")
    assert "export pass=" in content
    assert read_vault(path)["pass"] == value
    assert get_variable("secrets", "pass") == value


def test_preserve_spaces_in_value(config_dir: Path) -> None:
    """Values containing spaces round-trip correctly."""
    ensure_vault("notes")
    set_variable("notes", "desc", "hello world test")
    assert get_variable("notes", "desc") == "hello world test"


def test_parse_shell_value_variants() -> None:
    """parse_shell_value handles quoted and unquoted forms."""
    assert parse_shell_value("'10.10.10.1'") == "10.10.10.1"
    assert parse_shell_value('"hello world"') == "hello world"
    assert parse_shell_value("plain") == "plain"
    assert parse_shell_value("") == ""


def test_read_vault_ignores_comments_and_blank_lines(config_dir: Path) -> None:
    """Comments and blank lines are skipped when parsing."""
    path = vault_file_path("parsed")
    ensure_directories()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# comment\n\nexport ip='1.2.3.4'\n\nexport user=admin\n",
        encoding="utf-8",
    )
    variables = read_vault(path)
    assert variables == {"ip": "1.2.3.4", "user": "admin"}


def test_list_vaults(config_dir: Path) -> None:
    """list_vaults returns sorted vault names."""
    ensure_vault("beta")
    ensure_vault("alpha")
    assert list_vaults() == ["alpha", "beta"]


def test_rename_vault(config_dir: Path) -> None:
    """Vaults can be renamed on disk."""
    ensure_vault("oldname")
    set_variable("oldname", "ip", "10.0.0.1")
    rename_vault("oldname", "newname")
    assert not vault_file_path("oldname").exists()
    assert get_variable("newname", "ip") == "10.0.0.1"


def test_rename_existing_target_fails(config_dir: Path) -> None:
    """Renaming to an existing vault raises VaultExistsError."""
    ensure_vault("a")
    ensure_vault("b")
    with pytest.raises(VaultExistsError):
        rename_vault("a", "b")


def test_duplicate_vault(config_dir: Path) -> None:
    """duplicate_vault copies all variables."""
    ensure_vault("source")
    set_variable("source", "ip", "10.10.10.10")
    set_variable("source", "user", "admin")
    duplicate_vault("source", "copy")
    assert get_variable("copy", "ip") == "10.10.10.10"
    assert get_variable("copy", "user") == "admin"


def test_delete_vault(config_dir: Path) -> None:
    """delete_vault removes the vault file."""
    ensure_vault("todelete")
    delete_vault("todelete")
    with pytest.raises(VaultNotFoundError):
        delete_vault("todelete")


def test_clear_vault(config_dir: Path) -> None:
    """clear_vault removes all variables but keeps the file."""
    ensure_vault("clearme")
    set_variable("clearme", "ip", "1.1.1.1")
    clear_vault("clearme")
    assert read_vault(vault_file_path("clearme")) == {}


@pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions not enforced on Windows")
def test_directory_permissions(config_dir: Path) -> None:
    """Config and vault directories are created with mode 700."""
    ensure_directories()
    assert stat.S_IMODE(os.stat(config_dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(config_dir / "vaults").st_mode) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions not enforced on Windows")
def test_vault_file_permissions(config_dir: Path) -> None:
    """Vault files are written with mode 600."""
    path = ensure_vault("secure")
    set_variable("secure", "token", "abc")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_write_vault_sorted_keys(config_dir: Path) -> None:
    """Vault files write keys in sorted order."""
    write_vault(vault_file_path("sorted"), {"zebra": "z", "alpha": "a"})
    lines = vault_file_path("sorted").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("export alpha=")
    assert lines[1].startswith("export zebra=")
