"""Tests for validation helpers."""

from __future__ import annotations

import io

import pytest

from ctx.errors import ValidationError
from ctx.validation import validate_key_name, validate_vault_name, warn_value


def test_valid_vault_names() -> None:
    """Accepted vault names pass validation."""
    for name in ("forest", "htb-box", "lab_1", "client.eng"):
        validate_vault_name(name)


def test_invalid_vault_names() -> None:
    """Rejected vault names raise ValidationError."""
    for name in ("", "../etc", "foo/bar", "bad name", "vault$"):
        with pytest.raises(ValidationError):
            validate_vault_name(name)


def test_valid_key_names() -> None:
    """Accepted variable keys pass validation."""
    for key in ("ip", "_private", "user2", "RHOST"):
        validate_key_name(key)


def test_invalid_key_names() -> None:
    """Rejected keys raise ValidationError."""
    for key in ("", "2bad", "bad-key", "bad.key"):
        with pytest.raises(ValidationError):
            validate_key_name(key)


def test_warn_invalid_ip(capsys: pytest.CaptureFixture[str]) -> None:
    """Invalid IP values produce stderr warnings."""
    stream = io.StringIO()
    warn_value("ip", "not-an-ip", stream=stream)
    assert "does not look like an IPv4 address" in stream.getvalue()


def test_warn_invalid_port(capsys: pytest.CaptureFixture[str]) -> None:
    """Out-of-range ports produce stderr warnings."""
    stream = io.StringIO()
    warn_value("port", "99999", stream=stream)
    assert "outside range 1-65535" in stream.getvalue()


def test_warn_invalid_url() -> None:
    """Malformed URLs produce stderr warnings."""
    stream = io.StringIO()
    warn_value("url", "not-a-url", stream=stream)
    assert "does not look like a URL" in stream.getvalue()


def test_warn_invalid_domain() -> None:
    """Malformed domains produce stderr warnings."""
    stream = io.StringIO()
    warn_value("domain", "-bad..", stream=stream)
    assert "does not look like a hostname" in stream.getvalue()


def test_warn_empty_user() -> None:
    """Empty user values produce warnings."""
    stream = io.StringIO()
    warn_value("user", "   ", stream=stream)
    assert "should not be empty" in stream.getvalue()


def test_warn_valid_ip_no_warning() -> None:
    """Valid IPs produce no warning."""
    stream = io.StringIO()
    warn_value("ip", "10.10.10.161", stream=stream)
    assert stream.getvalue() == ""


def test_warn_arbitrary_key_no_warning() -> None:
    """Unknown keys do not produce validation warnings."""
    stream = io.StringIO()
    warn_value("custom_field", "anything", stream=stream)
    assert stream.getvalue() == ""
