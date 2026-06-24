"""Vault file storage, parsing, and permission management."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional

from ctx.errors import (
    KeyNotFoundError,
    VaultExistsError,
    VaultNotFoundError,
)
from ctx.validation import validate_key_name, validate_vault_name

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ctx"
DEFAULT_VAULTS_DIR = DEFAULT_CONFIG_DIR / "vaults"

EXPORT_LINE_PATTERN = re.compile(
    r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$"
)

_config_dir: Path = DEFAULT_CONFIG_DIR
_vaults_dir: Path = DEFAULT_VAULTS_DIR


def set_config_dir(config_dir: Path) -> None:
    """Override the configuration directory (primarily for tests).

    Args:
        config_dir: Base configuration directory path.
    """
    global _config_dir, _vaults_dir
    _config_dir = config_dir
    _vaults_dir = config_dir / "vaults"


def get_config_dir() -> Path:
    """Return the base configuration directory."""
    return _config_dir


def get_vaults_dir() -> Path:
    """Return the vaults storage directory."""
    return _vaults_dir


def vault_file_path(vault_name: str) -> Path:
    """Resolve the filesystem path for a named vault.

    Args:
        vault_name: Vault identifier.

    Returns:
        Path to the vault .env file.
    """
    validate_vault_name(vault_name)
    return _vaults_dir / f"{vault_name}.env"


def ensure_directories() -> None:
    """Create config and vault directories with secure permissions."""
    _config_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(_config_dir, 0o700)
    _vaults_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(_vaults_dir, 0o700)


def parse_shell_value(raw: str) -> str:
    """Parse a shell assignment value without executing it.

    Args:
        raw: Raw value portion after '=' on an env line.

    Returns:
        Unquoted string value.
    """
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        parts = shlex.split(stripped, posix=True)
        if parts:
            return parts[0]
    except ValueError:
        pass
    if (
        (stripped.startswith("'") and stripped.endswith("'"))
        or (stripped.startswith('"') and stripped.endswith('"'))
    ) and len(stripped) >= 2:
        return stripped[1:-1]
    return stripped


def read_vault(path: Path) -> Dict[str, str]:
    """Read variables from a vault env file.

    Only lines matching export KEY=VALUE or KEY=VALUE are parsed.
    Comments and blank lines are ignored.

    Args:
        path: Path to the vault file.

    Returns:
        Dictionary of variable keys to values.
    """
    if not path.exists():
        return {}

    variables: Dict[str, str] = {}
    content = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = EXPORT_LINE_PATTERN.match(stripped)
        if not match:
            continue
        key, raw_value = match.groups()
        try:
            validate_key_name(key)
        except Exception:
            continue
        variables[key] = parse_shell_value(raw_value)
    return variables


def write_vault(path: Path, variables: Dict[str, str]) -> None:
    """Write variables to a vault env file with safe shell quoting.

    Args:
        path: Destination vault file path.
        variables: Variables to persist.
    """
    ensure_directories()
    lines: List[str] = []
    for key in sorted(variables):
        validate_key_name(key)
        quoted = shlex.quote(variables[key])
        lines.append(f"export {key}={quoted}")

    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def list_vaults() -> List[str]:
    """List all vault names sorted alphabetically.

    Returns:
        List of vault names (without .env suffix).
    """
    ensure_directories()
    names: List[str] = []
    for entry in sorted(_vaults_dir.glob("*.env")):
        names.append(entry.stem)
    return names


def vault_exists(vault_name: str) -> bool:
    """Check whether a vault file exists."""
    return vault_file_path(vault_name).exists()


def ensure_vault(vault_name: str) -> Path:
    """Create a vault file if it does not already exist.

    Used internally by create_vault. Prefer create_vault for user-facing creation.

    Args:
        vault_name: Vault to ensure.

    Returns:
        Path to the vault file.
    """
    validate_vault_name(vault_name)
    ensure_directories()
    path = vault_file_path(vault_name)
    if not path.exists():
        write_vault(path, {})
    else:
        os.chmod(path, 0o600)
    return path


def create_vault(vault_name: str) -> Path:
    """Create a new empty vault.

    Args:
        vault_name: Name for the new vault.

    Returns:
        Path to the new vault file.

    Raises:
        VaultExistsError: If the vault already exists.
    """
    validate_vault_name(vault_name)
    path = vault_file_path(vault_name)
    if path.exists():
        raise VaultExistsError(
            f"Vault '{vault_name}' already exists. Use 'ctx load {vault_name}' to load it."
        )
    return ensure_vault(vault_name)


def require_vault_path(vault_name: str) -> Path:
    """Return the path to an existing vault or raise VaultNotFoundError.

    Args:
        vault_name: Vault name to resolve.

    Returns:
        Path to the vault file.

    Raises:
        VaultNotFoundError: If the vault does not exist.
    """
    validate_vault_name(vault_name)
    path = vault_file_path(vault_name)
    if not path.exists():
        raise VaultNotFoundError(
            f"Vault '{vault_name}' does not exist. Create it with: ctx create {vault_name}"
        )
    return path


def get_variable(vault_name: str, key: str) -> str:
    """Retrieve a single variable from a vault.

    Args:
        vault_name: Vault containing the variable.
        key: Variable key.

    Returns:
        Variable value.

    Raises:
        KeyNotFoundError: If the key is not present.
    """
    validate_key_name(key)
    variables = read_vault(vault_file_path(vault_name))
    if key not in variables:
        raise KeyNotFoundError(f"Key '{key}' not found in vault '{vault_name}'.")
    return variables[key]


def set_variable(vault_name: str, key: str, value: str) -> None:
    """Set or update a variable in a vault.

    Args:
        vault_name: Target vault name.
        key: Variable key.
        value: Variable value.
    """
    validate_key_name(key)
    path = require_vault_path(vault_name)
    variables = read_vault(path)
    variables[key] = value
    write_vault(path, variables)


def unset_variable(vault_name: str, key: str) -> None:
    """Remove a variable from a vault.

    Args:
        vault_name: Target vault name.
        key: Variable key to remove.

    Raises:
        KeyNotFoundError: If the key is not present.
    """
    validate_key_name(key)
    path = vault_file_path(vault_name)
    if not path.exists():
        raise VaultNotFoundError(f"Vault '{vault_name}' does not exist.")
    variables = read_vault(path)
    if key not in variables:
        raise KeyNotFoundError(f"Key '{key}' not found in vault '{vault_name}'.")
    del variables[key]
    write_vault(path, variables)


def clear_vault(vault_name: str) -> None:
    """Remove all variables from a vault."""
    path = vault_file_path(vault_name)
    if not path.exists():
        raise VaultNotFoundError(f"Vault '{vault_name}' does not exist.")
    write_vault(path, {})


def delete_vault(vault_name: str) -> None:
    """Delete a vault file from disk.

    Args:
        vault_name: Vault to delete.

    Raises:
        VaultNotFoundError: If the vault does not exist.
    """
    path = vault_file_path(vault_name)
    if not path.exists():
        raise VaultNotFoundError(f"Vault '{vault_name}' does not exist.")
    path.unlink()


def rename_vault(old_name: str, new_name: str) -> None:
    """Rename a vault on disk.

    Args:
        old_name: Current vault name.
        new_name: New vault name.

    Raises:
        VaultNotFoundError: If the source vault does not exist.
        VaultExistsError: If the destination vault already exists.
    """
    validate_vault_name(old_name)
    validate_vault_name(new_name)
    old_path = vault_file_path(old_name)
    new_path = vault_file_path(new_name)
    if not old_path.exists():
        raise VaultNotFoundError(f"Vault '{old_name}' does not exist.")
    if new_path.exists():
        raise VaultExistsError(f"Vault '{new_name}' already exists.")
    old_path.rename(new_path)
    os.chmod(new_path, 0o600)


def duplicate_vault(source_name: str, dest_name: str) -> None:
    """Copy one vault to a new name.

    Args:
        source_name: Vault to copy from.
        dest_name: New vault name.

    Raises:
        VaultNotFoundError: If the source vault does not exist.
        VaultExistsError: If the destination vault already exists.
    """
    validate_vault_name(source_name)
    validate_vault_name(dest_name)
    source_path = vault_file_path(source_name)
    dest_path = vault_file_path(dest_name)
    if not source_path.exists():
        raise VaultNotFoundError(f"Vault '{source_name}' does not exist.")
    if dest_path.exists():
        raise VaultExistsError(f"Vault '{dest_name}' already exists.")
    variables = read_vault(source_path)
    write_vault(dest_path, variables)


def get_active_vault_from_env() -> Optional[str]:
    """Read the terminal-local active vault from the environment.

    Returns:
        Active vault name, or None if not set.
    """
    value = os.environ.get("CTX_ACTIVE_VAULT", "").strip()
    if not value:
        return None
    try:
        validate_vault_name(value)
    except Exception:
        return None
    return value


def require_active_vault() -> str:
    """Return the active vault name or raise NoActiveVaultError.

    Returns:
        Active vault name from CTX_ACTIVE_VAULT.

    Raises:
        NoActiveVaultError: If no active vault is set in this terminal.
    """
    from ctx.errors import NoActiveVaultError

    vault = get_active_vault_from_env()
    if vault is None:
        raise NoActiveVaultError(
            "No active vault in this terminal. Run 'ctx load <vault>' first."
        )
    return vault
