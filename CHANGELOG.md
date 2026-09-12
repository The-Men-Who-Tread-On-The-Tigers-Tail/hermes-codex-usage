# Changelog

## [0.2.0] - Unreleased

- Normalize quota windows as a flat, documented API contract.
- Deduplicate concurrent refreshes and back off repeated failures.
- Classify authentication failures without exposing RPC details.
- Add reusable fixtures, fake Codex server, custom-window status display, and CI plugin validation.

## [0.1.0] - Unreleased

- Add a read-only Hermes Desktop status-bar chip for Codex subscription quota.
- Add a detailed quota pane with remaining percentages and reset times.
- Read limits through `codex app-server --stdio` and `account/rateLimits/read`.
- Keep Codex authentication inside the Codex CLI; no OAuth files or tokens are read.
- Add stale-cache handling and sanitized unavailable states.
- Add credential-free tests and an opt-in live Codex integration test.
