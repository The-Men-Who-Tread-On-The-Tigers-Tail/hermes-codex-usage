# Hermes Codex Usage Plugin Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a standalone Hermes Desktop plugin that reads the authenticated ChatGPT/Codex subscription quota through the installed Codex CLI and displays remaining usage and reset times without reading or storing OAuth tokens.

**Architecture:** A small Python backend plugin launches `codex app-server --stdio`, performs the official JSON-RPC initialization handshake, calls `account/rateLimits/read`, normalizes the response, and caches it briefly. An uncompiled Hermes Desktop plugin calls the scoped backend route with `ctx.rest`, then renders a right-side pane, status-bar chip, and manual refresh action using `@hermes/plugin-sdk`.

**Tech Stack:** Python 3.9+, FastAPI/APIRouter supplied by Hermes, pytest, Codex CLI app-server JSON-RPC, plain JavaScript ESM, React/React Query through `@hermes/plugin-sdk`, shell install scripts, GitHub Actions.

---

## Current context and decisions

- Repository: `/Users/johann/data/workspace/my/hermes-codex-usage`
- Working plugin ID: `hermes-codex-usage`; the plugin folder, manifest name, desktop export ID, API namespace, and install target must all use this exact ID.
- Verified locally with `codex-cli 0.154.0`: `account/rateLimits/read` returns authenticated quota data.
- The app-server is experimental. Keep all protocol handling in one adapter so a future Codex protocol change is isolated.
- Never read `~/.codex/auth.json`, `~/.hermes/auth.json`, cookies, or bearer tokens. Codex owns authentication.
- Never return account IDs or raw provider payloads to the renderer. Expose only normalized quota data.
- Do not assume `primary` means 5-hour or `secondary` means weekly. Classify every window by `windowDurationMins`:
  - `300` → `five_hour`
  - `10080` → `weekly`
  - any other positive value → `custom`
- Preserve all entries from `rateLimitsByLimitId`. The account-wide `codex` entry and model-specific limit IDs may have different windows.
- Interpret `usedPercent` as used capacity and calculate `remainingPercent = clamp(100 - usedPercent, 0, 100)`.
- Cache successful responses for 60 seconds. Manual refresh bypasses the cache. Errors must not overwrite the last successful snapshot.
- MVP scope: read-only quota display. No notifications, forecasting, automated provider switching, direct ChatGPT HTTP calls, or token/cost estimation.

## Target repository layout

```text
hermes-codex-usage/
├── .github/
│   └── workflows/
│       └── test.yml
├── .hermes/
│   └── plans/
│       └── 2026-09-12_151707-hermes-codex-usage.md
├── dashboard/
│   ├── __init__.py
│   ├── codex_rpc.py
│   ├── manifest.json
│   ├── plugin_api.py
│   └── quota.py
├── desktop/
│   └── plugin.js
├── tests/
│   ├── fixtures/
│   │   ├── rate_limits_multi.json
│   │   ├── rate_limits_weekly_only.json
│   │   └── rpc_notifications.jsonl
│   ├── fake_codex.py
│   ├── test_codex_rpc.py
│   ├── test_plugin_api.py
│   └── test_quota.py
├── .gitignore
├── LICENSE
├── README.md
├── install.sh
├── uninstall.sh
├── plugin.yaml
└── pyproject.toml
```

## Normalized backend contract

`GET /api/plugins/hermes-codex-usage/quota` returns:

```json
{
  "success": true,
  "source": "codex-app-server",
  "fetchedAt": "2026-09-12T13:00:00Z",
  "stale": false,
  "planType": "prolite",
  "ordinaryUsageAllowed": true,
  "credits": {
    "hasCredits": false,
    "unlimited": false,
    "balance": "0"
  },
  "limits": [
    {
      "limitId": "codex",
      "limitName": null,
      "window": "weekly",
      "windowDurationMins": 10080,
      "usedPercent": 4.0,
      "remainingPercent": 96.0,
      "resetsAt": 1789808928
    }
  ]
}
```

On failure with no previous snapshot:

```json
{
  "success": false,
  "source": "codex-app-server",
  "fetchedAt": null,
  "stale": false,
  "error": {
    "code": "codex_not_found",
    "message": "Codex CLI was not found on PATH."
  },
  "limits": []
}
```

On refresh failure after a successful fetch, return the last snapshot with `stale: true` and a sanitized `refreshError`. Never expose stderr wholesale because it may contain paths or provider diagnostics.

---

### Task 1: Add repository metadata and test harness

**Objective:** Establish a minimal standalone Hermes plugin repository with deterministic local tests.

**Files:**
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `plugin.yaml`
- Create: `pyproject.toml`
- Create: `dashboard/__init__.py`
- Create: `dashboard/manifest.json`

**Steps:**

1. Add Python cache, virtual-environment, coverage, build, macOS, and editor artifacts to `.gitignore`.
2. Add an MIT license.
3. Define `plugin.yaml` with `name: hermes-codex-usage`, semantic version `0.1.0`, a read-only description, and the plugin kind required by the current Hermes plugin validator.
4. Define `dashboard/manifest.json` with `name: hermes-codex-usage`, label `Codex Usage`, version `0.1.0`, and `api: plugin_api.py`.
5. Add `pyproject.toml` with Python `>=3.9`, bounded development dependencies, pytest configuration, and no runtime dependency duplication for FastAPI supplied by Hermes.
6. Run `python3 -m pytest --collect-only`; expect successful collection with zero tests initially.
7. Run `hermes plugins validate .`; expect a successful manifest validation. If the current validator expects a different manifest field, update the metadata rather than bypassing validation.
8. Commit:

```bash
git add .gitignore LICENSE plugin.yaml pyproject.toml dashboard
 git commit -m "chore: scaffold Hermes Codex usage plugin"
```

---

### Task 2: Normalize Codex rate-limit payloads

**Objective:** Convert changing Codex app-server payload shapes into a small stable renderer contract.

**Files:**
- Create: `dashboard/quota.py`
- Create: `tests/fixtures/rate_limits_multi.json`
- Create: `tests/fixtures/rate_limits_weekly_only.json`
- Create: `tests/test_quota.py`

**Steps:**

1. Capture sanitized fixtures covering:
   - account-wide weekly-only `codex` usage;
   - a model-specific 5-hour and weekly pair;
   - missing credits and nullable metadata;
   - `usedPercent` values at and outside the expected 0–100 range.
2. Write failing tests for `normalize_rate_limits(payload, fetched_at)` asserting:
   - windows are classified by duration, never by primary/secondary position;
   - `rateLimitsByLimitId` is preferred when present;
   - the legacy `rateLimits` object is used only when the map is absent;
   - all identifiers are preserved exactly;
   - percentages are numeric and remaining values are clamped;
   - malformed windows are omitted rather than fabricated;
   - account IDs and unknown raw fields are absent from normalized output;
   - output order is deterministic: account-wide `codex` first, then limit ID, then shorter window.
3. Run `python3 -m pytest tests/test_quota.py -v`; expect failures because the normalizer does not exist.
4. Implement pure normalization helpers in `dashboard/quota.py`. Do not perform subprocess, network, filesystem, or clock access in this module.
5. Run `python3 -m pytest tests/test_quota.py -v`; expect all normalization tests to pass.
6. Commit:

```bash
git add dashboard/quota.py tests/fixtures tests/test_quota.py
git commit -m "feat: normalize Codex quota windows"
```

---

### Task 3: Implement the Codex app-server JSON-RPC client

**Objective:** Fetch rate limits through Codex-owned authentication without touching credential files.

**Files:**
- Create: `dashboard/codex_rpc.py`
- Create: `tests/fake_codex.py`
- Create: `tests/fixtures/rpc_notifications.jsonl`
- Create: `tests/test_codex_rpc.py`

**Steps:**

1. Write a fake Codex executable that reads newline-delimited JSON-RPC and can simulate:
   - successful initialization and quota response;
   - interleaved notifications before the matching response;
   - JSON-RPC error response;
   - malformed JSON;
   - early process exit;
   - timeout;
   - stderr output.
2. Write failing async tests for `CodexAppServerClient` asserting that it:
   - resolves `codex` with `shutil.which` or accepts an injected executable for tests;
   - launches an argument list, never `shell=True`;
   - sends `initialize`, then `initialized`, then `account/rateLimits/read`;
   - matches responses by request ID and ignores notifications;
   - enforces a configurable timeout;
   - terminates and reaps the child process on every path;
   - maps failures to typed, sanitized exceptions (`codex_not_found`, `auth_required`, `rpc_error`, `invalid_response`, `timeout`);
   - never includes complete stderr or raw JSON in user-facing error messages.
3. Run `python3 -m pytest tests/test_codex_rpc.py -v`; expect failures.
4. Implement the smallest async subprocess client using `asyncio.create_subprocess_exec`, newline-delimited JSON, explicit request IDs, and bounded reads.
5. Run `python3 -m pytest tests/test_codex_rpc.py -v`; expect all tests to pass and no orphan `fake_codex.py` process.
6. Commit:

```bash
git add dashboard/codex_rpc.py tests/fake_codex.py tests/fixtures/rpc_notifications.jsonl tests/test_codex_rpc.py
git commit -m "feat: read quota through Codex app-server"
```

---

### Task 4: Add cache and stale-data behavior

**Objective:** Prevent repeated app-server launches while keeping the last known quota visible through temporary failures.

**Files:**
- Modify: `dashboard/quota.py`
- Modify: `tests/test_quota.py`

**Steps:**

1. Write failing tests for a `QuotaService` with injected client and clock:
   - repeated calls within 60 seconds invoke the client once;
   - `force=True` bypasses the cache;
   - concurrent refreshes share one in-flight request;
   - a refresh error after success returns the previous snapshot with `stale: true` and `refreshError`;
   - an initial error returns `success: false` and no fabricated timestamps;
   - failed fetches are briefly backoff-cached to avoid spawning on every renderer repaint.
2. Run the focused tests and confirm they fail.
3. Implement `QuotaService` with an `asyncio.Lock`, monotonic cache age, UTC presentation timestamps, 60-second success TTL, and short failure backoff.
4. Run `python3 -m pytest tests/test_quota.py -v`; expect pass.
5. Commit:

```bash
git add dashboard/quota.py tests/test_quota.py
git commit -m "feat: cache quota snapshots safely"
```

---

### Task 5: Expose the scoped Hermes backend API

**Objective:** Make normalized quota data available only through the plugin’s Hermes-scoped REST namespace.

**Files:**
- Create: `dashboard/plugin_api.py`
- Create: `tests/test_plugin_api.py`

**Steps:**

1. Inspect the current Hermes dashboard plugin loader to confirm whether sibling imports should be package-relative or loaded by explicit file path; use the supported loading pattern.
2. Write failing route tests for:
   - `GET /quota` using the normal cache;
   - `POST /quota/refresh` forcing a refresh;
   - stable HTTP 200 responses for provider/auth failures so the desktop can render an error card;
   - unexpected internal failures returning a sanitized response without traceback, account ID, token, or raw stderr.
3. Run `python3 -m pytest tests/test_plugin_api.py -v`; expect failures.
4. Implement an `APIRouter` and one process-local `QuotaService`. Keep route handlers thin; subprocess and normalization logic remain in their own modules.
5. Run `python3 -m pytest tests/test_plugin_api.py -v`; expect pass.
6. Load the plugin through a temporary `HERMES_HOME` and verify `/api/plugins/hermes-codex-usage/quota` mounts under the expected namespace.
7. Commit:

```bash
git add dashboard/plugin_api.py tests/test_plugin_api.py
git commit -m "feat: expose Codex quota API"
```

---

### Task 6: Build the Hermes Desktop quota pane

**Objective:** Render complete quota data in a native, resize-safe Hermes pane.

**Files:**
- Create: `desktop/plugin.js`

**Steps:**

1. Export a desktop plugin with ID `hermes-codex-usage` and import only `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`.
2. Register a right-side pane titled `Codex Usage` through `PANES_AREA`.
3. Fetch `/quota` using the SDK’s shared `useQuery` with a 60-second interval. Do not implement a manual polling loop.
4. Render:
   - plan badge;
   - account-wide and model-specific cards grouped by `limitId`;
   - progress bars for each five-hour, weekly, or custom window;
   - used and remaining percentages;
   - absolute local reset time and live relative reset text;
   - loading, missing-Codex, signed-out, stale-data, and generic unavailable states;
   - a refresh button invoking `POST /quota/refresh` and invalidating the shared query.
5. Use Hermes UI components and theme variables. Do not hardcode colors, backgrounds, or JSX syntax; the shipped file is uncompiled ESM and must use `jsx`/`jsxs`.
6. Check every identifier used in `jsx()` calls is imported.
7. Reload desktop plugins and verify the pane loads without an error toast, follows light/dark themes, and remains usable when narrowed.
8. Commit:

```bash
git add desktop/plugin.js
git commit -m "feat: add Codex usage pane"
```

---

### Task 7: Add status-bar summary and command-palette refresh

**Objective:** Surface the most actionable subscription limit without requiring the pane to stay open.

**Files:**
- Modify: `desktop/plugin.js`

**Steps:**

1. Register a `statusBar.right` contribution that reuses the exact same React Query key as the pane.
2. Select the display summary deterministically:
   - prefer account-wide `codex` windows;
   - show both 5-hour and weekly when available;
   - when only one window exists, label it by duration;
   - never relabel a weekly-only primary window as a session window.
3. Render a compact chip such as `Codex · W 96% left`; clicking it opens a popover with all limits.
4. Register a command-palette action `Refresh Codex usage` that calls the force-refresh route and reports success or sanitized failure with `host.notify`.
5. Verify pane and status bar deduplicate requests through the shared query cache and do not poll twice.
6. Commit:

```bash
git add desktop/plugin.js
git commit -m "feat: add Codex quota status chip"
```

---

### Task 8: Add installation and removal workflows

**Objective:** Install the unified backend and desktop plugin safely without modifying Hermes source.

**Files:**
- Create: `install.sh`
- Create: `uninstall.sh`
- Modify: `.gitignore`

**Steps:**

1. Implement `install.sh` to resolve `HERMES_HOME` with `${HERMES_HOME:-$HOME/.hermes}` and copy the repository’s plugin runtime files into `$HERMES_HOME/plugins/hermes-codex-usage/`.
2. Exclude `.git`, tests, local plans, caches, and development files from the installed copy.
3. Refuse to overwrite an unrelated directory. For an existing installation created by this project, replace runtime files atomically using a staging directory.
4. Do not edit `config.yaml` directly. After installation, print the exact supported `hermes plugins enable hermes-codex-usage` command and gateway reload/restart guidance.
5. Implement `uninstall.sh` to remove only the exact plugin directory after verifying its manifest name; do not delete persistent state outside that directory.
6. Test both scripts against a temporary `HERMES_HOME`, then run `hermes plugins validate` on the installed copy.
7. Commit:

```bash
git add install.sh uninstall.sh .gitignore
git commit -m "feat: add safe plugin installer"
```

---

### Task 9: Add real integration verification

**Objective:** Prove the complete adapter works with a real authenticated Codex installation while keeping CI credential-free.

**Files:**
- Create: `tests/test_live_codex.py`
- Modify: `pyproject.toml`

**Steps:**

1. Add a pytest `live_codex` marker disabled by default.
2. Write a live test that:
   - skips if `codex` is missing;
   - invokes the real app-server client;
   - asserts at least one valid normalized limit or a typed authentication error;
   - asserts no account ID or token-shaped field survives normalization;
   - does not assert current percentages, plan names, number of buckets, or specific model IDs.
3. Run unit tests:

```bash
python3 -m pytest -m "not live_codex" -v
```

Expected: all tests pass without network or credentials.

4. Run the live test locally:

```bash
python3 -m pytest -m live_codex -v
```

Expected on this machine: pass with the authenticated Codex account.

5. Install into a temporary `HERMES_HOME`, start the Hermes backend, and read back the exact scoped endpoint. Verify no credential or account identifier appears in the response or logs.
6. Commit:

```bash
git add tests/test_live_codex.py pyproject.toml
git commit -m "test: verify live Codex quota integration"
```

---

### Task 10: Document setup, compatibility, and privacy

**Objective:** Make installation, operation, and failure recovery clear to a new user.

**Files:**
- Create: `README.md`
- Create: `.github/workflows/test.yml`

**Steps:**

1. Document prerequisites: Hermes Desktop, Codex CLI with ChatGPT login, and supported Python version.
2. Document install, enable, gateway restart, desktop plugin reload, update, and uninstall commands.
3. Explain that the plugin invokes Codex app-server and never reads or stores OAuth tokens.
4. Explain the experimental-protocol compatibility risk and the visible error states.
5. Document development commands, fixture tests, and the opt-in live test.
6. Add CI for supported Python versions, running credential-free tests and `hermes plugins validate` where practical. Pin GitHub Actions by full commit SHA with version comments.
7. Run final verification:

```bash
python3 -m pytest -m "not live_codex" -v
python3 -m pytest -m live_codex -v
hermes plugins validate .
git diff --check
git status --short
```

Expected: all tests and validation pass; `git diff --check` is clean; only intentional files are present.

8. Perform a manual Hermes Desktop acceptance pass:
   - pane appears and is draggable;
   - status chip appears;
   - refresh updates data;
   - percentage labels match normalized API data;
   - reset times use the local timezone;
   - offline refresh leaves the last good snapshot visible and marked stale;
   - signed-out and missing-Codex cases are actionable;
   - no error toast or console exception occurs.
9. Commit:

```bash
git add README.md .github/workflows/test.yml
git commit -m "docs: document Codex usage plugin"
```

---

## Acceptance criteria

- The plugin obtains subscription quota exclusively through Codex CLI app-server authentication.
- No OAuth token, cookie, ChatGPT account ID, or raw provider payload is read, persisted, logged, or returned to the renderer.
- All available rate-limit IDs and windows are represented.
- Five-hour and weekly windows are classified by duration, not by field position.
- The pane and status-bar chip show remaining percentages and reset times.
- Refreshes are cached, concurrent calls are deduplicated, and temporary failures retain a stale last-known snapshot.
- Missing CLI, signed-out account, timeout, malformed protocol response, and provider errors render actionable states without crashing Hermes.
- Installation is profile-safe through `HERMES_HOME` and does not modify Hermes core files or hand-edit `config.yaml`.
- Unit tests are credential-free; a separate opt-in live test validates the actual installed Codex CLI.
- The installed plugin passes `hermes plugins validate` and is manually verified in Hermes Desktop.

## Risks and tradeoffs

- **Experimental app-server protocol:** isolate request/response handling and test with fixtures; show a compatibility error instead of falling back to direct token access.
- **Codex executable visibility:** the gateway’s launch environment may have a narrower PATH than the interactive shell. Detect and report the resolved executable; later add a non-secret configured executable path only if this occurs in real use.
- **Multiple quota products:** do not collapse model-specific limits into one misleading number. The status chip is a summary; the pane remains authoritative.
- **Provider semantics:** percentages and quota IDs are backend-controlled. Preserve labels and durations, and avoid inventing allowances.
- **Process cost:** a short-lived app-server launch is acceptable at a 60-second cache interval for the MVP. A persistent daemon connection is unnecessary until measurements show a problem.
- **Remote Hermes gateway:** the backend executes Codex where the gateway runs, not necessarily on the desktop machine. The UI must explain when Codex is missing on that host.

## Deferred ideas

- Threshold notifications.
- Usage history and forecasting.
- Hermes agent-accessible quota tool.
- TUI widget and messaging `/codex-usage` command.
- Multi-account selection.
- Persistent app-server daemon connection.
- Direct contribution to Hermes’ shared provider account-usage abstraction.
