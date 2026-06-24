"""Custom exceptions for the ctx application."""


class CtxError(Exception):
    """Base exception for ctx errors."""


class ValidationError(CtxError):
    """Raised when user input fails validation."""


class NoActiveVaultError(CtxError):
    """Raised when a command requires an active vault but none is set."""


class VaultNotFoundError(CtxError):
    """Raised when a requested vault does not exist."""


class VaultExistsError(CtxError):
    """Raised when creating a vault that already exists."""


class KeyNotFoundError(CtxError):
    """Raised when a variable key is not present in the vault."""


class OperationCancelledError(CtxError):
    """Raised when the user declines a confirmation prompt."""
