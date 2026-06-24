"""Shell integration helpers used by the Python backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from ctx.storage import vault_file_path


def resolve_editor() -> List[str]:
    """Resolve an editor command to invoke for ctx edit.

    Prefers $EDITOR, then nano, then vi.

    Returns:
        Command argv list suitable for subprocess.run.

    Raises:
        RuntimeError: If no suitable editor is found.
    """
    candidates: List[str] = []
    editor_env = os.environ.get("EDITOR", "").strip()
    if editor_env:
        candidates.append(editor_env)
    candidates.extend(["nano", "vi"])

    for candidate in candidates:
        parts = candidate.split()
        if not parts:
            continue
        executable = parts[0]
        if shutil.which(executable):
            return parts
    raise RuntimeError("No editor found. Set $EDITOR or install nano/vi.")


def open_vault_in_editor(vault_path: Path) -> None:
    """Open a vault file in the user's editor.

    Restores file permissions to 600 after editing.

    Args:
        vault_path: Path to the vault env file.
    """
    editor_cmd = resolve_editor()
    result = subprocess.run([*editor_cmd, str(vault_path)], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Editor exited with status {result.returncode}.")
    if vault_path.exists():
        os.chmod(vault_path, 0o600)


def confirm(prompt: str, force: bool) -> bool:
    """Prompt the user for yes/no confirmation.

    Args:
        prompt: Confirmation message.
        force: If True, skip prompting and return True.

    Returns:
        True if confirmed, False otherwise.
    """
    if force:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    return answer in ("y", "yes")


def print_vault_path_for_active() -> int:
    """Print the filesystem path for the active vault.

    Used by shell integration for ``ctx load``, ``ctx unload``, and auto-reload after ``ctx set``.

    Returns:
        Exit code (0 on success).
    """
    from ctx.errors import CtxError, NoActiveVaultError
    from ctx.storage import require_active_vault

    try:
        vault = require_active_vault()
        path = vault_file_path(vault)
        if not path.exists():
            print(
                f"error: vault file for '{vault}' does not exist.",
                file=sys.stderr,
            )
            return 1
        print(path)
        return 0
    except CtxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
