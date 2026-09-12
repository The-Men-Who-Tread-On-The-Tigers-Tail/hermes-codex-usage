"""Opt-in live test for the locally authenticated Codex CLI."""
import shutil

import pytest

from dashboard.codex_rpc import CodexAppServerClient, CodexUsageError
from dashboard.quota import normalize_rate_limits


@pytest.mark.live_codex
@pytest.mark.asyncio
async def test_authenticated_codex_rate_limits_are_normalizable():
    if shutil.which("codex") is None:
        pytest.skip("codex CLI is not installed")
    try:
        payload = await CodexAppServerClient().read_rate_limits()
    except CodexUsageError as exc:
        if exc.code in {"auth_required", "rpc_error"}:
            pytest.skip(f"Codex authentication unavailable: {exc.code}")
        raise
    result = normalize_rate_limits(payload)
    assert result["success"] is True
    assert isinstance(result["limits"], list)
    assert "accountId" not in str(result)
