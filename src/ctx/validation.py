"""Validation helpers for vault names, keys, and common variable values."""

from __future__ import annotations

import re
import sys
from typing import Optional, TextIO

from ctx.errors import ValidationError

VAULT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
KEY_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
PORT_PATTERN = re.compile(r"^\d+$")
URL_PATTERN = re.compile(r"^https?://[^\s/]+(?:/[^\s]*)?$", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)

IP_KEYS = frozenset({"ip", "rhost", "lhost", "target", "dc_ip", "gateway"})
PORT_KEYS = frozenset({"port", "rport", "lport"})
URL_KEYS = frozenset({"url", "uri"})
DOMAIN_KEYS = frozenset({"domain", "host", "hostname", "fqdn", "dc"})
USER_KEYS = frozenset({"user", "username"})
SECRET_KEYS = frozenset({"pass", "password", "token", "hash", "secret", "key"})


def validate_vault_name(name: str) -> None:
    """Validate a vault name against the allowed pattern.

    Args:
        name: Vault name to validate.

    Raises:
        ValidationError: If the name is empty or contains invalid characters.
    """
    if not name:
        raise ValidationError("Vault name cannot be empty.")
    if not VAULT_NAME_PATTERN.match(name):
        raise ValidationError(
            "Invalid vault name. Use only letters, digits, underscore, dot, and hyphen."
        )


def validate_key_name(key: str) -> None:
    """Validate a shell variable key name.

    Args:
        key: Variable key to validate.

    Raises:
        ValidationError: If the key is not a valid shell identifier.
    """
    if not key:
        raise ValidationError("Variable key cannot be empty.")
    if not KEY_NAME_PATTERN.match(key):
        raise ValidationError(
            f"Invalid key '{key}'. Keys must match ^[A-Za-z_][A-Za-z0-9_]*$."
        )


def warn_value(key: str, value: str, stream: Optional[TextIO] = None) -> None:
    """Emit a validation warning for a key/value pair without blocking.

    Warnings are written to stderr. The command should still succeed.

    Args:
        key: Variable key being set.
        value: Variable value being set.
        stream: Output stream for warnings; defaults to sys.stderr.
    """
    out = stream if stream is not None else sys.stderr
    normalized = key.lower()

    if normalized in IP_KEYS:
        if not IPV4_PATTERN.match(value):
            print(
                f"warning: '{key}' does not look like an IPv4 address: {value}",
                file=out,
            )
        return

    if normalized in PORT_KEYS:
        if not PORT_PATTERN.match(value):
            print(f"warning: '{key}' is not an integer: {value}", file=out)
            return
        port = int(value)
        if port < 1 or port > 65535:
            print(
                f"warning: '{key}' port {port} is outside range 1-65535",
                file=out,
            )
        return

    if normalized in URL_KEYS:
        if not URL_PATTERN.match(value):
            print(f"warning: '{key}' does not look like a URL: {value}", file=out)
        return

    if normalized in DOMAIN_KEYS:
        if not DOMAIN_PATTERN.match(value):
            print(
                f"warning: '{key}' does not look like a hostname or domain: {value}",
                file=out,
            )
        return

    if normalized in USER_KEYS:
        if not value.strip():
            print(f"warning: '{key}' should not be empty", file=out)
        return

    if normalized in SECRET_KEYS:
        if not value:
            print(f"warning: '{key}' should not be empty", file=out)
