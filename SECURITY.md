# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.x | Yes |

## Reporting a Vulnerability

Please do not open a public issue for security vulnerabilities.

Use GitHub private vulnerability reporting if available, or contact the maintainer directly.

When reporting, include:

- ctx version
- operating system and shell
- install method
- reproduction steps
- expected behavior
- observed behavior
- whether the issue affects vault parsing, shell export generation, file permissions, locking, installer/uninstaller behavior, or shell integration

## Security Model

ctx stores vaults as plaintext local files. It does not provide encryption in v1.

Vault files are parsed by the Python backend and are not directly sourced by the shell. The shell integration applies backend-generated export/unset statements.

Exported environment variables are visible to child processes. Do not store secrets in ctx unless this operational tradeoff is acceptable.
