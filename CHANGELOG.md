# Changelog

## [0.1.0] - Unreleased

- Add a read-only Hermes Desktop status-bar chip for Codex subscription quota.
- Add a detailed quota pane with remaining percentages and reset times.
- Read limits through `codex app-server --stdio` and `account/rateLimits/read`.
- Keep Codex authentication inside the Codex CLI; no OAuth files or tokens are read.
- Add stale-cache handling and sanitized unavailable states.
- Add credential-free tests and an opt-in live Codex integration test.
