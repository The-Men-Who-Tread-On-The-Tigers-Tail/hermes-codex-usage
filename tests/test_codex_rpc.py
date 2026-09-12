import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from dashboard.codex_rpc import CodexAppServerClient, CodexUsageError


@pytest.fixture
def fake_codex(tmp_path):
    path = tmp_path / "codex"
    path.write_text('''#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("method") == "initialize":
        print(json.dumps({"id": msg["id"], "result": {"ok": True}}), flush=True)
        print(json.dumps({"method": "notification", "params": {}}), flush=True)
    elif msg.get("method") == "account/rateLimits/read":
        print(json.dumps({"method": "notification", "params": {}}), flush=True)
        print(json.dumps({"id": msg["id"], "result": {"planType": "pro", "rateLimits": {"limitId": "codex", "primary": {"usedPercent": 3, "windowDurationMins": 300}}}}), flush=True)
''')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.mark.asyncio
async def test_client_matches_json_rpc_responses_and_ignores_notifications(fake_codex, monkeypatch):
    monkeypatch.setattr("dashboard.codex_rpc.shutil.which", lambda _: str(fake_codex))
    result = await CodexAppServerClient(executable="codex").read_rate_limits()
    assert result["planType"] == "pro"
    assert result["rateLimits"]["primary"]["usedPercent"] == 3


@pytest.mark.asyncio
async def test_client_reports_missing_executable(monkeypatch):
    monkeypatch.setattr("dashboard.codex_rpc.shutil.which", lambda _: None)
    with pytest.raises(CodexUsageError, match="not found") as exc:
        await CodexAppServerClient().read_rate_limits()
    assert exc.value.code == "codex_not_found"
