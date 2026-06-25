"""Command-line interface for the ctx backend (ctxctl)."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from typing import Optional, Sequence

from ctx import __version__
from ctx.errors import (
    CtxError,
    KeyNotFoundError,
    NoActiveVaultError,
    OperationCancelledError,
    ValidationError,
    VaultExistsError,
    VaultNotFoundError,
)
from ctx.formatting import format_show
from ctx.shell import confirm, open_vault_in_editor, print_vault_path_for_active
from ctx.storage import (
    clear_vault,
    create_vault,
    delete_vault,
    duplicate_vault,
    get_variable,
    list_vaults,
    read_vault,
    read_vault_strict,
    rename_vault,
    require_active_vault,
    require_vault_path,
    set_variable,
    unset_variable,
    vault_file_path,
    vault_exists,
)
from ctx.validation import (
    validate_key_name,
    validate_value,
    validate_vault_name,
    warn_value,
)

EPILOG = """
Shell integration:
  ctx load, ctx unload, and ctx set are handled by the shell function.
  ctx load <vault> loads a vault and unloads the previous vault when switching.
  ctx load (no vault) reloads the active vault's variables from disk.
  ctx unload removes loaded vault variables from this shell session.
  ctx set, ctx unset, and ctx clear automatically reload the vault after a
  successful change so the shell environment stays in sync.
  Source shell/ctx.sh or shell/ctx.zsh and use the 'ctx' command in your shell.

Examples:
  ctx create forest
  ctx load forest
  ctx set ip 10.10.10.161
  ctx load sauna
  echo $ip
  ctx unload
"""


def _join_value(parts: Sequence[str]) -> str:
    """Join value tokens from argparse REMAINDER into a single string."""
    if not parts:
        return ""
    return " ".join(parts)


def cmd_current(_args: argparse.Namespace) -> int:
    """Show the terminal-local active vault."""
    from ctx.storage import get_active_vault_from_env

    vault = get_active_vault_from_env()
    if vault is None:
        print(
            "No active vault in this terminal. Run 'ctx load <vault>' first.",
            file=sys.stderr,
        )
        return 1
    print(vault)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    """List all vaults."""
    vaults = list_vaults()
    if not vaults:
        print("No vaults found.")
        return 0
    for name in vaults:
        print(name)
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new empty vault."""
    create_vault(args.vault)
    print(f"Created vault '{args.vault}'.")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    """Verify vault exists or active vault is set (shell loads into session)."""
    if args.vault:
        require_vault_path(args.vault)
    else:
        vault = require_active_vault()
        require_vault_path(vault)
    return 0


def cmd_unload(_args: argparse.Namespace) -> int:
    """Placeholder; unloading is performed by the shell function."""
    print(
        "error: ctx unload must be run from the ctx shell function.",
        file=sys.stderr,
    )
    return 1


def cmd_set(args: argparse.Namespace) -> int:
    """Set a variable in the active vault.

    When invoked via the ctx shell function, the vault is auto-reloaded into
    the terminal after a successful write so shell variables stay current.
    """
    vault = require_active_vault()
    validate_key_name(args.key)
    value = _join_value(args.value)
    validate_value(value)
    warn_value(args.key, value)
    set_variable(vault, args.key, value)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    """Get a variable value from the active vault."""
    vault = require_active_vault()
    value = get_variable(vault, args.key)
    print(value)
    return 0


def cmd_unset(args: argparse.Namespace) -> int:
    """Remove a variable from the active vault."""
    vault = require_active_vault()
    unset_variable(vault, args.key)
    return 0


def cmd_show(_args: argparse.Namespace) -> int:
    """Display the active vault and all variables."""
    vault = require_active_vault()
    variables = read_vault(vault_file_path(vault))
    print(format_show(vault, variables))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """Clear all variables from the active vault."""
    vault = require_active_vault()
    if not confirm(
        f"Clear all variables in vault '{vault}'?",
        args.force,
    ):
        print("Cancelled.", file=sys.stderr)
        return 1
    clear_vault(vault)
    return 0


def cmd_path(_args: argparse.Namespace) -> int:
    """Print the active vault file path."""
    vault = require_active_vault()
    print(vault_file_path(vault))
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a named vault."""
    validate_vault_name(args.vault)
    if not vault_exists(args.vault):
        raise VaultNotFoundError(f"Vault '{args.vault}' does not exist.")
    if not confirm(
        f"Delete vault '{args.vault}' and all its variables?",
        args.force,
    ):
        print("Cancelled.", file=sys.stderr)
        return 1
    delete_vault(args.vault)
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    """Rename a vault."""
    rename_vault(args.old, args.new)
    return 0


def cmd_duplicate(args: argparse.Namespace) -> int:
    """Duplicate a vault."""
    duplicate_vault(args.old, args.new)
    return 0


def cmd_edit(_args: argparse.Namespace) -> int:
    """Open the active vault in $EDITOR."""
    vault = require_active_vault()
    path = require_vault_path(vault)
    open_vault_in_editor(path)
    return 0


def cmd_shell_path(_args: argparse.Namespace) -> int:
    """Internal: print active vault path for shell reload helpers."""
    return print_vault_path_for_active()


def cmd_shell_keys(_args: argparse.Namespace) -> int:
    """Internal: list variable keys in the active vault for completions."""
    vault = require_active_vault()
    variables = read_vault(vault_file_path(vault))
    for key in sorted(variables):
        print(key)
    return 0


def cmd_shell_keys_for(args: argparse.Namespace) -> int:
    """Internal: list variable keys for a named vault (shell unload helper)."""
    validate_vault_name(args.vault)
    variables = read_vault(vault_file_path(args.vault))
    for key in sorted(variables):
        print(key)
    return 0


def _previously_loaded_keys() -> set[str]:
    """Determine which variable keys are currently loaded from a ctx vault.

    The set is tracked across loads in CTX_LOADED_KEYS so that the next load
    can unset them, even on a same-vault reload after a key was removed (via
    ``ctx unset``/``ctx clear`` or a manual edit). Falls back to the keys of
    the previously loaded vault file for shells started before CTX_LOADED_KEYS
    existed.

    Returns:
        Set of validated key names previously exported by ctx.
    """
    prev_keys: set[str] = set()
    for token in os.environ.get("CTX_LOADED_KEYS", "").split():
        try:
            validate_key_name(token)
        except Exception:
            continue
        prev_keys.add(token)

    if prev_keys:
        return prev_keys

    prev_loaded = os.environ.get("CTX_LOADED_VAULT", "").strip()
    if prev_loaded:
        try:
            validate_vault_name(prev_loaded)
        except Exception:
            return prev_keys
        if vault_exists(prev_loaded):
            prev_keys = set(read_vault(vault_file_path(prev_loaded)))
    return prev_keys


def cmd_shell_load(args: argparse.Namespace) -> int:
    """Internal: emit sanitized shell code to (un)load a vault safely.

    This command prints shell code intended to be eval'd by bash/zsh shell
    integration. It never sources the user-editable vault file directly.

    The full script is built in memory and only printed once the target vault
    has been fully validated, so a malformed/unsafe vault changes nothing in
    the shell. Variables previously loaded by ctx are unset first (tracked via
    CTX_LOADED_KEYS) so stale variables disappear on unset/clear/same-vault
    reload, while switching vaults still clears the old set.
    """
    validate_vault_name(args.vault)
    path = require_vault_path(args.vault)

    prev_keys = _previously_loaded_keys()

    # Validate/parse the target BEFORE emitting anything so failures are inert.
    variables = read_vault_strict(path)
    for key in variables:
        validate_key_name(key)

    lines: list[str] = [f"unset {key}" for key in sorted(prev_keys)]
    lines += [
        f"export {key}={shlex.quote(variables[key])}" for key in sorted(variables)
    ]
    lines.append(f"export CTX_LOADED_VAULT={shlex.quote(args.vault)}")
    lines.append(f"export CTX_LOADED_KEYS={shlex.quote(' '.join(sorted(variables)))}")
    print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="ctx",
        description="Lightweight terminal context and vault variable manager.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ctx {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.required = False

    p_current = subparsers.add_parser(
        "current",
        help="show active vault for this terminal",
        description="Show the vault loaded with 'ctx load' in this terminal.",
    )
    p_current.set_defaults(func=cmd_current)

    p_list = subparsers.add_parser(
        "list",
        help="list all vaults",
        description="List all stored vault names.",
    )
    p_list.set_defaults(func=cmd_list)

    p_create = subparsers.add_parser(
        "create",
        help="create a new empty vault",
        description="Create a new vault file. Does not load it; run 'ctx load' after creating.",
    )
    p_create.add_argument("vault", help="vault name")
    p_create.set_defaults(func=cmd_create)

    p_load = subparsers.add_parser(
        "load",
        help="load a vault into this shell (shell integration)",
        description=(
            "Load an existing vault into the shell. With a vault name, selects that "
            "vault, unloads any previously loaded vault, and applies its variables. "
            "Without a vault name, reloads the active vault's variables from disk. "
            "Fails if the vault does not exist; use 'ctx create' first."
        ),
    )
    p_load.add_argument(
        "vault",
        nargs="?",
        help="vault name (optional; reloads the active vault if omitted)",
    )
    p_load.set_defaults(func=cmd_load)

    p_unload = subparsers.add_parser(
        "unload",
        help="unload vault variables from this shell (shell integration)",
        description=(
            "Remove all variables from the currently loaded vault from this shell "
            "session. Does not delete the vault file on disk."
        ),
    )
    p_unload.set_defaults(func=cmd_unload)

    p_set = subparsers.add_parser(
        "set",
        help="set a variable in the active vault (auto-reloads via shell)",
        description=(
            "Set or update a variable in the active vault. "
            "The ctx shell function automatically reloads the vault after "
            "each successful set so $variables are immediately available."
        ),
    )
    p_set.add_argument("key", help="variable name")
    p_set.add_argument(
        "value",
        nargs=argparse.REMAINDER,
        help="variable value (quote if it contains spaces)",
    )
    p_set.set_defaults(func=cmd_set)

    p_get = subparsers.add_parser(
        "get",
        help="get a variable from the active vault",
        description="Print the value of a variable in the active vault.",
    )
    p_get.add_argument("key", help="variable name")
    p_get.set_defaults(func=cmd_get)

    p_unset = subparsers.add_parser(
        "unset",
        help="remove a variable from the active vault",
        description="Remove a variable from the active vault.",
    )
    p_unset.add_argument("key", help="variable name")
    p_unset.set_defaults(func=cmd_unset)

    p_show = subparsers.add_parser(
        "show",
        help="show active vault and all variables",
        description="Display the active vault name and all stored variables.",
    )
    p_show.set_defaults(func=cmd_show)

    p_clear = subparsers.add_parser(
        "clear",
        help="clear all variables in the active vault",
        description="Remove every variable from the active vault.",
    )
    p_clear.add_argument(
        "--force",
        action="store_true",
        help="skip confirmation prompt",
    )
    p_clear.set_defaults(func=cmd_clear)

    p_path = subparsers.add_parser(
        "path",
        help="print active vault file path",
        description="Print the filesystem path to the active vault env file.",
    )
    p_path.set_defaults(func=cmd_path)

    p_delete = subparsers.add_parser(
        "delete",
        help="delete a vault",
        description="Permanently delete a vault and its variables.",
    )
    p_delete.add_argument("vault", help="vault name to delete")
    p_delete.add_argument(
        "--force",
        action="store_true",
        help="skip confirmation prompt",
    )
    p_delete.set_defaults(func=cmd_delete)

    p_rename = subparsers.add_parser(
        "rename",
        help="rename a vault",
        description="Rename an existing vault.",
    )
    p_rename.add_argument("old", help="current vault name")
    p_rename.add_argument("new", help="new vault name")
    p_rename.set_defaults(func=cmd_rename)

    p_duplicate = subparsers.add_parser(
        "duplicate",
        help="copy a vault",
        description="Duplicate an existing vault under a new name.",
    )
    p_duplicate.add_argument("old", help="source vault name")
    p_duplicate.add_argument("new", help="destination vault name")
    p_duplicate.set_defaults(func=cmd_duplicate)

    p_edit = subparsers.add_parser(
        "edit",
        help="edit active vault in $EDITOR",
        description="Open the active vault file in $EDITOR (nano or vi fallback).",
    )
    p_edit.set_defaults(func=cmd_edit)

    p_shell = subparsers.add_parser(
        "_shell",
        help=argparse.SUPPRESS,
        description=argparse.SUPPRESS,
    )
    shell_sub = p_shell.add_subparsers(dest="shell_command", required=True)

    p_shell_path = shell_sub.add_parser("path", help=argparse.SUPPRESS)
    p_shell_path.set_defaults(func=cmd_shell_path)

    p_shell_keys = shell_sub.add_parser("keys", help=argparse.SUPPRESS)
    p_shell_keys.set_defaults(func=cmd_shell_keys)

    p_shell_keys_for = shell_sub.add_parser("keys-for", help=argparse.SUPPRESS)
    p_shell_keys_for.add_argument("vault", help=argparse.SUPPRESS)
    p_shell_keys_for.set_defaults(func=cmd_shell_keys_for)

    p_shell_load = shell_sub.add_parser("load", help=argparse.SUPPRESS)
    p_shell_load.add_argument("vault", help=argparse.SUPPRESS)
    p_shell_load.set_defaults(func=cmd_shell_load)

    return parser


def handle_error(exc: Exception) -> int:
    """Map exceptions to user-facing error messages and exit codes."""
    if isinstance(exc, ValidationError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, NoActiveVaultError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, VaultNotFoundError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, VaultExistsError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, KeyNotFoundError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, OperationCancelledError):
        print("Cancelled.", file=sys.stderr)
        return 1
    if isinstance(exc, CtxError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if isinstance(exc, RuntimeError):
        print(f"error: {exc}", file=sys.stderr)
        return 1
    raise exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ctxctl console script.

    Args:
        argv: Optional argument list; defaults to sys.argv[1:].

    Returns:
        Process exit code.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return int(args.func(args))
    except Exception as exc:
        return handle_error(exc)


if __name__ == "__main__":
    sys.exit(main())
