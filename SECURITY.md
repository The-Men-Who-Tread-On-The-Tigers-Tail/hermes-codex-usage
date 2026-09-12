# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected security vulnerability. Contact the repository owner privately through the GitHub security advisory mechanism or the contact method listed on the repository profile.

Include a description of the issue, affected files or versions, reproduction steps, and potential impact. Do not include passwords, OAuth tokens, cookies, or other credentials.

## Scope

The plugin is intended to be read-only. It delegates authentication to the locally installed Codex CLI and must not read or transmit Codex OAuth files, Hermes authentication files, cookies, bearer tokens, or raw account identifiers.
