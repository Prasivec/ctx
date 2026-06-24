"""Output formatting helpers for ctx commands."""

from __future__ import annotations

from typing import Dict


def format_show(vault_name: str, variables: Dict[str, str]) -> str:
    """Format vault contents for display.

    Args:
        vault_name: Name of the active vault.
        variables: Mapping of variable keys to values.

    Returns:
        Human-readable multi-line string for terminal output.
    """
    lines = [f"vault: {vault_name}"]
    if not variables:
        lines.append("(empty)")
        return "\n".join(lines)

    max_key = max(len(key) for key in variables)
    for key in sorted(variables):
        lines.append(f"{key.ljust(max_key)}  {variables[key]}")
    return "\n".join(lines)
