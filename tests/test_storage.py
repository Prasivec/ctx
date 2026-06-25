"""Tests for vault storage, parsing, and permissions."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from ctx.errors import (
    KeyNotFoundError,
    ValidationError,
    VaultExistsError,
    VaultNotFoundError,
)
from ctx.storage import (
    acquire_vault_lock,
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


def test_default_config_dir_uses_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """XDG_CONFIG_HOME should override ~/.config for default config dir."""
    from ctx import storage as storage_mod

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    resolved = storage_mod.default_config_dir()
    assert resolved == (tmp_path / "xdg" / "ctx")


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
    value = 'Password123! $pecial "chars"'
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix file permissions not enforced on Windows"
)
def test_directory_permissions(config_dir: Path) -> None:
    """Config and vault directories are created with mode 700."""
    ensure_directories()
    assert stat.S_IMODE(os.stat(config_dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(config_dir / "vaults").st_mode) == 0o700


@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix file permissions not enforced on Windows"
)
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix file permissions not enforced on Windows"
)
def test_write_vault_is_atomic_and_preserves_permissions(config_dir: Path) -> None:
    """write_vault should atomically replace the target and keep mode 600."""
    ensure_vault("atomic")
    path = vault_file_path("atomic")
    path.write_text("export ip='1.1.1.1'\n", encoding="utf-8")
    os.chmod(path, 0o600)

    write_vault(path, {"ip": "2.2.2.2"})
    assert "2.2.2.2" in path.read_text(encoding="utf-8")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl locking is Unix-only")
def test_write_lock_blocks_other_writers(config_dir: Path) -> None:
    """A held advisory lock should cause a second writer to fail quickly."""
    import fcntl

    from ctx.storage import _lock_file_path

    ensure_vault("locked")
    lock_path = _lock_file_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError) as exc:
            set_variable("locked", "ip", "10.0.0.2")
        assert "locked" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Full-transaction advisory locking
# ---------------------------------------------------------------------------


def test_sequential_locked_updates(config_dir: Path) -> None:
    """Repeated locked updates apply cleanly without leaving stale lock state."""
    ensure_vault("seq")
    for i in range(5):
        set_variable("seq", "ip", f"10.0.0.{i}")
    assert get_variable("seq", "ip") == "10.0.0.4"
    # The lock must be released after each transaction; a fresh write succeeds.
    set_variable("seq", "user", "admin")
    assert get_variable("seq", "user") == "admin"


def test_two_updates_to_different_keys_preserve_both(config_dir: Path) -> None:
    """Independent read-modify-write updates must not clobber each other."""
    ensure_vault("multi")
    set_variable("multi", "ip", "10.10.10.10")
    set_variable("multi", "user", "operator")
    variables = read_vault(vault_file_path("multi"))
    assert variables == {"ip": "10.10.10.10", "user": "operator"}


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl locking is Unix-only")
def test_lock_acquire_and_release(config_dir: Path) -> None:
    """acquire_vault_lock yields a valid fd and releases it on exit."""
    ensure_directories()
    with acquire_vault_lock() as fd:
        assert isinstance(fd, int)
        assert fd >= 0
    # After release, the same process can take the lock again immediately.
    with acquire_vault_lock() as fd2:
        assert fd2 >= 0


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl locking is Unix-only")
def test_lock_already_held_raises(config_dir: Path) -> None:
    """Holding the lock makes a second acquisition fail with a clear error."""
    ensure_directories()
    with acquire_vault_lock():
        with pytest.raises(RuntimeError) as exc:
            with acquire_vault_lock(timeout_s=0.1):
                pass
    assert "locked" in str(exc.value).lower()


def test_mutations_do_not_deadlock(config_dir: Path) -> None:
    """Public mutation functions must not double-acquire the lock."""
    ensure_vault("nodl")
    set_variable("nodl", "ip", "1.1.1.1")
    set_variable("nodl", "user", "admin")
    unset_variable("nodl", "user")
    clear_vault("nodl")
    duplicate_vault("nodl", "nodl2")
    rename_vault("nodl2", "nodl3")
    delete_vault("nodl3")
    assert read_vault(vault_file_path("nodl")) == {}


# ---------------------------------------------------------------------------
# Atomic write / parent-directory fsync
# ---------------------------------------------------------------------------


def test_failed_write_does_not_corrupt_original(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the atomic replace fails, the original vault content is preserved."""
    ensure_vault("safe")
    set_variable("safe", "ip", "1.1.1.1")
    path = vault_file_path("safe")
    original = path.read_text(encoding="utf-8")

    import ctx.storage as storage_mod

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(storage_mod.os, "replace", boom)
    with pytest.raises(OSError):
        set_variable("safe", "ip", "2.2.2.2")

    # Original file is untouched and no temp files linger in the vault dir.
    assert path.read_text(encoding="utf-8") == original
    leftovers = [p for p in path.parent.glob(".safe.env.*") if p.suffix == ".tmp"]
    assert leftovers == []


def test_fsync_dir_helper_is_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_fsync_dir flushes a directory and tolerates platform limitations."""
    from ctx.storage import _fsync_dir

    # Exercises the happy path (real dir) without raising.
    _fsync_dir(tmp_path)

    # A non-existent directory must be handled gracefully (no exception).
    _fsync_dir(tmp_path / "does-not-exist")


# ---------------------------------------------------------------------------
# Single-line value policy
# ---------------------------------------------------------------------------


def test_set_rejects_newline_value(config_dir: Path) -> None:
    """Values containing a literal newline are rejected."""
    ensure_vault("nl")
    with pytest.raises(ValidationError):
        set_variable("nl", "note", "line1\nline2")
    # The vault must not have been corrupted.
    assert read_vault(vault_file_path("nl")) == {}


def test_set_rejects_carriage_return_value(config_dir: Path) -> None:
    """Values containing a carriage return are rejected."""
    ensure_vault("cr")
    with pytest.raises(ValidationError):
        set_variable("cr", "note", "line1\rline2")
    assert read_vault(vault_file_path("cr")) == {}


def test_set_accepts_single_line_metacharacters(config_dir: Path) -> None:
    """Shell metacharacters are fine as single-line values."""
    ensure_vault("meta")
    value = "p@ss word; $(id) `id` (x) $HOME ' \" |&"
    set_variable("meta", "secret", value)
    assert get_variable("meta", "secret") == value
