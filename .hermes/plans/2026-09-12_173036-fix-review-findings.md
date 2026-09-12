# Review Findings Remediation Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Resolve all 12 findings from the whole-project Standards and Spec review, align the backend contract with the original specification, and publish a verified `v0.2.0` release.

**Architecture:** Keep the existing short-lived Codex app-server adapter, but make its errors explicitly typed, normalize every rate-limit window into one flat record, and make `QuotaService` own success caching, in-flight deduplication, and failure backoff. The desktop continues to display grouped cards, but derives those groups from the flat API response and uses one shared query hook/configuration for both pane and status chip.

**Tech Stack:** Python 3.9+, asyncio, FastAPI `APIRouter`, pytest/pytest-asyncio, plain ESM JavaScript using the Hermes Desktop plugin SDK, GitHub Actions, uv.

---

## Current context and decisions

- Review base: empty Git tree `4b825dc642cb6eb9a060e54bf8d69288fbee4904`.
- Current release: `v0.1.1`; remediation release: `v0.2.0` because the internal normalized API shape changes.
- The live-proven `~/.local/bin/codex` fallback stays. It was not in the original MVP plan, but the real Hermes launch environment reproduced the narrow-`PATH` problem anticipated in the plan's risk section. Document this as a resolved runtime requirement rather than removing working behavior.
- Preserve the security boundary: no direct OAuth-file reads, no token handling, no raw stderr or provider payloads in renderer responses.
- Keep the plugin's grouped pane UX. Only the backend contract becomes flat; grouping belongs in the renderer.
- Do not introduce a persistent Codex daemon.

## Target normalized API contract

Each available window becomes one record:

```json
{
  "success": true,
  "source": "codex-app-server",
  "fetchedAt": "2026-09-12T15:00:00+00:00",
  "stale": false,
  "planType": "prolite",
  "ordinaryUsageAllowed": true,
  "credits": null,
  "limits": [
    {
      "limitId": "codex",
      "limitName": null,
      "window": "weekly",
      "windowDurationMins": 10080,
      "usedPercent": 5.0,
      "remainingPercent": 95.0,
      "resetsAt": 1789808928
    }
  ]
}
```

Ordering remains deterministic: account-wide `codex` first, then other IDs; within one ID, shorter duration first.

---

### Task 1: Replace embedded RPC test data with reusable fixtures

**Objective:** Add the fixture artifacts required by the original spec and cover every Codex subprocess failure mode without credentials.

**Files:**
- Create: `tests/fake_codex.py`
- Create: `tests/fixtures/rate_limits_multi.json`
- Create: `tests/fixtures/rate_limits_weekly_only.json`
- Create: `tests/fixtures/rpc_notifications.jsonl`
- Modify: `tests/test_codex_rpc.py`
- Modify: `tests/test_quota.py`

**Step 1: Create deterministic fixture payloads**

`rate_limits_multi.json` must contain account-wide weekly quota plus model/product-specific five-hour and weekly windows. `rate_limits_weekly_only.json` must contain only a 10,080-minute primary window. Use synthetic IDs and reset timestamps only.

**Step 2: Create a configurable fake Codex executable**

Implement `tests/fake_codex.py` so environment variable `FAKE_CODEX_MODE` selects:

```python
MODES = {
    "success",
    "rpc_auth_error",
    "rpc_error",
    "malformed_json",
    "early_exit",
    "timeout",
    "stderr_noise",
}
```

It must read newline-delimited requests from stdin, emit an initialization response, optionally interleave lines from `rpc_notifications.jsonl`, and emit the selected terminal response. It must never access real credentials or the network.

**Step 3: Rewrite the RPC fixture setup**

Copy `tests/fake_codex.py` to a temporary executable path and set `FAKE_CODEX_MODE` per test. Remove the embedded Python script from `tests/test_codex_rpc.py`.

**Step 4: Add failing tests for all required process paths**

Add focused async tests for successful notification skipping, generic RPC error, auth error, malformed JSON, early exit, timeout, stderr noise, and executable cleanup. Assert only typed codes and sanitized messages.

**Step 5: Run tests and confirm the new cases fail where behavior is missing**

```bash
uv run --extra test pytest tests/test_codex_rpc.py tests/test_quota.py -v
```

Expected: fixture plumbing passes; auth classification and any uncovered process paths fail before later tasks.

**Step 6: Commit**

```bash
git add tests/fake_codex.py tests/fixtures tests/test_codex_rpc.py tests/test_quota.py
git commit -m "test: add deterministic Codex protocol fixtures"
```

---

### Task 2: Align normalization with the flat API contract

**Objective:** Represent every available Codex window as one privacy-safe limit record and remove the ambiguous `_number` name.

**Files:**
- Modify: `dashboard/quota.py`
- Modify: `tests/test_quota.py`

**Step 1: Rewrite normalization assertions first**

Tests must expect a flat `limits` list and assert this invariant:

```python
assert [(item["limitId"], item["window"]) for item in result["limits"]] == [
    ("codex", "weekly"),
    ("codex_bengalfox", "five_hour"),
    ("codex_bengalfox", "weekly"),
]
```

Also assert custom windows, clamping, malformed durations, deterministic ordering, and absence of `accountId` or unknown credit fields.

**Step 2: Run the normalization tests and verify failure**

```bash
uv run --extra test pytest tests/test_quota.py -k normal -v
```

Expected: FAIL because production still emits nested `windows` arrays.

**Step 3: Implement the flat contract**

- Rename `_number` to `_parse_finite_number`.
- Reject non-finite values with `math.isfinite`, including positive/negative infinity.
- Append one output dictionary per valid primary/secondary window.
- Keep `limitName` on every record.
- Sort with:

```python
limits.sort(key=lambda item: (
    0 if item["limitId"] == "codex" else 1,
    item["limitId"],
    item["windowDurationMins"],
    item["window"],
))
```

**Step 4: Run focused tests**

```bash
uv run --extra test pytest tests/test_quota.py -k normal -v
```

Expected: all selected tests pass.

**Step 5: Commit**

```bash
git add dashboard/quota.py tests/test_quota.py
git commit -m "refactor: flatten normalized quota windows"
```

---

### Task 3: Classify authentication failures explicitly

**Objective:** Emit `auth_required` only for confirmed Codex authentication failures while keeping all messages sanitized.

**Files:**
- Modify: `dashboard/codex_rpc.py`
- Modify: `tests/test_codex_rpc.py`

**Step 1: Inspect the installed Codex app-server error schema**

Use the current Codex source/help or a credential-free fixture to identify the stable code/data marker for an unauthenticated `account/rateLimits/read` response. Do not infer auth state from arbitrary substrings alone.

**Step 2: Add failing classifier tests**

Cover a confirmed auth-shaped JSON-RPC error and a similarly worded generic error. The latter must remain `rpc_error`.

**Step 3: Add a narrow classifier**

```python
def _rpc_error_code(error: Any) -> str:
    if isinstance(error, dict) and _is_confirmed_auth_error(error):
        return "auth_required"
    return "rpc_error"
```

The raised user-facing text must be fixed text:

```python
messages = {
    "auth_required": "Codex CLI is not signed in.",
    "rpc_error": "Codex rejected the usage request.",
}
```

Never include `error["message"]`, raw JSON, or stderr.

**Step 4: Run focused tests**

```bash
uv run --extra test pytest tests/test_codex_rpc.py -v
```

Expected: all RPC tests pass.

**Step 5: Commit**

```bash
git add dashboard/codex_rpc.py tests/test_codex_rpc.py
git commit -m "fix: classify Codex authentication failures"
```

---

### Task 4: Deduplicate concurrent fetches and back off failures

**Objective:** Guarantee one in-flight Codex process per service and prevent renderer repaint loops from repeatedly spawning failed requests.

**Files:**
- Modify: `dashboard/quota.py`
- Modify: `tests/test_quota.py`

**Step 1: Add failing concurrency tests**

Use an event-controlled fake client. Start multiple `get()` calls and multiple `refresh()` calls before releasing the client. Assert `client.calls == 1` and that every caller receives the same result.

**Step 2: Add failing backoff tests**

Inject a clock and configure `failure_ttl=5`. Assert:

- an initial failure is reused within five seconds;
- a stale snapshot plus `refreshError` is reused during backoff;
- a call after five seconds retries;
- a manual `refresh()` bypasses failure backoff but still joins an already-running request.

**Step 3: Implement explicit in-flight ownership**

Use one stored task/future rather than relying solely on a lock:

```python
self._inflight: Optional[asyncio.Task[Dict[str, Any]]] = None
self._failure_result: Optional[Dict[str, Any]] = None
self._failure_cached_at = 0.0
self.failure_ttl = failure_ttl
```

`get()` checks success cache, then failure cache, then joins or creates `_inflight`. Clear `_inflight` in `finally`. Cache sanitized failure/stale results only after the request completes.

**Step 4: Run focused tests**

```bash
uv run --extra test pytest tests/test_quota.py -v
```

Expected: all cache, stale, concurrency, and backoff tests pass deterministically.

**Step 5: Commit**

```bash
git add dashboard/quota.py tests/test_quota.py
git commit -m "fix: deduplicate quota fetches and back off failures"
```

---

### Task 5: Remove duplicated backend error payloads

**Objective:** Keep endpoint handlers thin without changing their endpoint-specific messages.

**Files:**
- Modify: `dashboard/plugin_api.py`
- Modify: `tests/test_plugin_api.py`

**Step 1: Add behavior assertions**

Assert both endpoint failure shapes, including endpoint-specific text and identical invariant fields.

**Step 2: Extract one helper**

```python
def _internal_error(message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "source": "codex-app-server",
        "fetchedAt": None,
        "stale": False,
        "error": {"code": "internal_error", "message": message},
        "limits": [],
    }
```

Handlers retain their broad exception boundary because this is the security sanitization boundary.

**Step 3: Run route tests**

```bash
uv run --extra test pytest tests/test_plugin_api.py -v
```

Expected: pass with no internal exception strings returned.

**Step 4: Commit**

```bash
git add dashboard/plugin_api.py tests/test_plugin_api.py
git commit -m "refactor: centralize sanitized API errors"
```

---

### Task 6: Centralize desktop query behavior and adapt to flat limits

**Objective:** Remove duplicated query configuration, remove the no-op pane wrapper, and preserve grouped rendering over the new flat API.

**Files:**
- Modify: `desktop/plugin.js`

**Step 1: Introduce one shared hook**

```js
function useQuotaQuery() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => rest
      ? rest('/quota')
      : Promise.resolve({ success: false, limits: [], error: { message: 'Backend unavailable' } }),
    refetchInterval: POLL_MS,
    retry: 1
  })
}
```

Use it in both `UsageContent` and `StatusChip`.

**Step 2: Group flat records for pane cards**

Add a pure `groupLimits(limits)` helper returning `{ limitId, limitName, windows }` objects. Keep deterministic order from the API and render each record with the existing `LimitRow`.

**Step 3: Remove the middle-man component**

Delete `UsagePane` and register `render: () => jsx(UsageContent, {})` directly.

**Step 4: Verify syntax before further UI changes**

```bash
node --check desktop/plugin.js
```

Expected: exit 0.

**Step 5: Commit**

```bash
git add desktop/plugin.js
git commit -m "refactor: share desktop quota query behavior"
```

---

### Task 7: Correct refresh semantics, notifications, and custom summaries

**Objective:** Finish all desktop behavior required by the original spec.

**Files:**
- Modify: `desktop/plugin.js`
- Modify: `README.md`

**Step 1: Import and retain the Hermes host**

Add `host` to the `@hermes/plugin-sdk` import.

**Step 2: Invalidate after force refresh**

```js
async function refresh({ notify = false } = {}) {
  if (!rest) throw new Error('Backend unavailable')
  const data = await rest('/quota/refresh', { method: 'POST' })
  queryClient.setQueryData(QUERY_KEY, data)
  await queryClient.invalidateQueries({ queryKey: QUERY_KEY })
  if (!data.success) throw new Error(data.error?.message || 'Codex usage unavailable')
  if (notify) host.notify({ kind: 'success', message: 'Codex usage refreshed.' })
  return data
}
```

The command wrapper catches failures and calls:

```js
host.notify({ kind: 'error', message: 'Codex usage could not be refreshed.' })
```

Do not display unsanitized thrown details.

**Step 3: Support custom-only summaries**

`selectStatusWindows()` must prefer account-wide records, fill missing five-hour/weekly records from other IDs, and if neither standard duration exists select the shortest available custom duration. Label it with duration, for example `90m 72%` or `24h 72%`.

**Step 4: Preserve request deduplication**

The pane and chip must call only `useQuotaQuery()`. Refresh invalidation may issue one cached GET, but must not start an extra Codex process because the backend success cache is fresh.

**Step 5: Update user documentation**

Document palette refresh success/failure feedback and custom-window labels.

**Step 6: Verify manually in Hermes Desktop**

- status chip shows 5-hour and weekly values;
- clicking opens the upward popover;
- palette refresh shows success notification;
- simulated error shows only sanitized failure notification;
- a custom-only fixture produces a duration label;
- pane and chip display the same percentages.

**Step 7: Commit**

```bash
git add desktop/plugin.js README.md
git commit -m "fix: complete desktop refresh and quota summaries"
```

---

### Task 8: Pin CI and restore Hermes validation

**Objective:** Make CI satisfy the documented release requirements without depending on a preinstalled local Hermes CLI.

**Files:**
- Modify: `.github/workflows/test.yml`

**Step 1: Add a supported Python matrix**

Use Python `3.9`, `3.11`, and `3.13` for credential-free Python tests. Run desktop syntax and shell checks once on Python 3.11.

**Step 2: Pin actions by full SHA**

Use the currently resolved immutable pins:

```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
- uses: astral-sh/setup-uv@e58605a9b6da7c637471fab8847a5e5a6b8df081 # v5
```

**Step 3: Add pinned Hermes validation**

Hermes Agent `0.21.2` is not available at its PyPI JSON endpoint, so validate from an immutable Git revision:

```yaml
- name: Validate Hermes plugin
  if: matrix.python-version == '3.11'
  run: >-
    uvx --from
    'git+https://github.com/NousResearch/hermes-agent.git@b7b35a84b7fbe1aa2e223a6ce726a2471300d0a4'
    hermes plugins validate .
```

If the CLI entry-point syntax differs in a clean runner, fix the command—not the pin—and prove it in a container or GitHub Actions before merging.

**Step 4: Keep credential-free boundaries**

CI must run `pytest -m 'not live_codex'`; never add Codex credentials or execute the live test in Actions.

**Step 5: Validate workflow syntax and run equivalent local checks**

```bash
uv run --extra test pytest -m 'not live_codex' -q
node --check desktop/plugin.js
sh -n install.sh uninstall.sh
hermes plugins validate .
```

Expected: all pass.

**Step 6: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: pin actions and validate the Hermes plugin"
```

---

### Task 9: Update versioning and release documentation

**Objective:** Document the resolved findings and prepare a coherent `v0.2.0` release.

**Files:**
- Modify: `plugin.yaml`
- Modify: `dashboard/manifest.json`
- Modify: `pyproject.toml`
- Modify: `dashboard/codex_rpc.py`
- Modify: `CHANGELOG.md`
- Modify: `README.md`

**Step 1: Centralize or synchronize version declarations**

Set all shipped metadata and Codex `clientInfo.version` to `0.2.0`. Add a test in `tests/test_metadata.py` that parses runtime metadata and asserts the declarations agree; test values relationally rather than freezing `0.2.0` forever.

**Step 2: Document the accepted PATH fallback**

Explain that Hermes may launch with a narrower PATH and that the plugin checks executable resolution in this order:

1. `shutil.which('codex')`;
2. executable `~/.local/bin/codex` for the default command only;
3. sanitized `codex_not_found` error.

This closes the scope-creep finding by making the live-discovered behavior an explicit requirement.

**Step 3: Update the changelog**

Move `0.1.0` out of `Unreleased`, add `0.2.0`, and list flat contract, failure backoff, auth classification, refresh notifications, custom summaries, test fixtures, and CI hardening.

**Step 4: Run metadata tests**

```bash
uv run --extra test pytest tests/test_metadata.py -v
```

Expected: all version declarations match.

**Step 5: Commit**

```bash
git add plugin.yaml dashboard/manifest.json pyproject.toml dashboard/codex_rpc.py CHANGELOG.md README.md tests/test_metadata.py
git commit -m "chore: prepare v0.2.0 release"
```

---

### Task 10: Execute full local and installed verification

**Objective:** Prove the complete source, installation, backend, live adapter, and desktop UI before publishing.

**Files:**
- No production changes expected; fix failures in the owning task's files.

**Step 1: Run credential-free suite**

```bash
uv run --extra test pytest -m 'not live_codex' -v
```

Expected: all tests pass with no credentials or network.

**Step 2: Run live Codex integration**

```bash
uv run --extra test pytest -m live_codex -v
```

Expected on the maintainer machine: pass using the currently authenticated Codex CLI; no account ID or credential-shaped field in normalized output.

**Step 3: Run syntax and package checks**

```bash
uv run python -m py_compile __init__.py dashboard/*.py tests/*.py
node --check desktop/plugin.js
sh -n install.sh uninstall.sh
hermes plugins validate .
git diff --check
```

Expected: every command exits 0.

**Step 4: Verify a fresh temporary installation**

Install into a temporary `HERMES_HOME`, verify exact runtime files, run `hermes plugins validate` against the installed copy, and load `dashboard/plugin_api.py` through the same standalone `importlib.util.spec_from_file_location` path Hermes uses. Assert routes `/quota` and `/quota/refresh` are present.

**Step 5: Verify subprocess cleanup**

Run success, timeout, malformed JSON, RPC error, and early-exit fixtures; confirm no fake Codex child remains after each test.

**Step 6: Manual desktop acceptance pass**

Verify:

- `Codex · 5h N% · W N%` appears;
- popover opens upward on click;
- all limit IDs/windows appear in grouped cards;
- custom-only limit gets a duration label;
- reset times are local;
- refresh notification works;
- stale last-known data survives a temporary failure;
- signed-out, missing CLI, malformed response, timeout, and generic provider failures are actionable and sanitized;
- no renderer console errors or Hermes error toast.

**Step 7: Review the final diff**

Run a two-axis review from `v0.1.1...HEAD` against this remediation plan and the project standards. Resolve all hard findings and re-evaluate smell findings before release.

---

### Task 11: Publish `v0.2.0`

**Objective:** Ship the remediated project only after local and GitHub verification are green.

**Files:**
- No additional source changes expected.

**Step 1: Push the branch**

```bash
git push origin HEAD
```

**Step 2: Verify GitHub Actions**

```bash
gh run list --repo The-Men-Who-Tread-On-The-Tigers-Tail/hermes-codex-usage --limit 5
gh run watch <RUN_ID> --repo The-Men-Who-Tread-On-The-Tigers-Tail/hermes-codex-usage --exit-status
```

Expected: all matrix jobs and Hermes validation succeed.

**Step 3: Create the release**

```bash
gh release create v0.2.0 \
  --repo The-Men-Who-Tread-On-The-Tigers-Tail/hermes-codex-usage \
  --title 'v0.2.0 — Reliability and contract alignment' \
  --generate-notes
```

**Step 4: Read back external state**

Verify repository visibility, `origin/main`, release URL/tag, CI conclusion, and clean local status before reporting success.

---

## Finding-to-task traceability

| Review finding | Remediation task |
|---|---:|
| Missing fixture artifacts | 1 |
| Missing concurrent in-flight sharing | 4 |
| Missing failure backoff | 4 |
| Nested normalized contract differs from spec | 2, 6 |
| Missing `auth_required` | 3 |
| Refresh does not invalidate shared query | 7 |
| Palette refresh lacks notifications | 7 |
| Custom-only status summary omitted | 7 |
| CI actions not SHA-pinned | 8 |
| CI omits Hermes validation | 8 |
| PATH fallback classified as scope creep | 9 (document as live-proven requirement) |
| Duplicated backend error payloads | 5 |
| Duplicated desktop query config | 6 |
| No-op `UsagePane` middle man | 6 |
| `_number` mysterious name | 2 |

## Risks and tradeoffs

- **Contract change:** Flat normalization changes the internal `/quota` response. Backend and desktop ship together, but release as `v0.2.0` and document it.
- **Auth classification:** Avoid substring-only classification; false `auth_required` states are worse than a generic provider error.
- **Concurrency complexity:** Store one in-flight task with explicit cleanup. Do not combine a lock and task ownership in a way that can deadlock or retain a failed task.
- **Failure backoff:** Keep it short (default five seconds). Manual refresh should bypass cached failure but join an existing request.
- **CI cost:** Installing Hermes from pinned Git may be slower. Run it on one matrix job only.
- **Fixture drift:** Fixtures model a protocol that is experimental. Keep raw synthetic fixture shape close to actual Codex responses without copying account data.

## Completion criteria

- Every review finding maps to an implemented task or an explicit documented decision.
- All credential-free, live, installer, syntax, and Hermes validation checks pass.
- The API returns one record per available window.
- Concurrent callers share one process; failures observe bounded backoff.
- The desktop uses one query helper, supports custom-only windows, invalidates on refresh, and reports command outcomes.
- GitHub Actions use immutable SHA pins and validate the plugin.
- `v0.2.0` is published only after CI and the final two-axis review pass.
