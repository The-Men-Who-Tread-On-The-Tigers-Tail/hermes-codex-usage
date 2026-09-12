import asyncio

import pytest

from dashboard.quota import QuotaService, normalize_rate_limits
from dashboard.codex_rpc import CodexUsageError


def test_normalizes_duration_and_keeps_all_limit_ids():
    result = normalize_rate_limits({
        "planType": "prolite",
        "rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 4, "windowDurationMins": 10080, "resetsAt": 123}},
            "codex_bengalfox": {
                "primary": {"usedPercent": 110, "windowDurationMins": 300, "resetsAt": 456},
                "secondary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": 789},
            },
        },
        "accountId": "must-not-leak",
        "credits": {"hasCredits": False, "unlimited": False, "balance": "0", "secret": "x"},
    }, fetched_at="2026-01-01T00:00:00+00:00")
    assert [x["limitId"] for x in result["limits"]] == ["codex", "codex_bengalfox"]
    assert result["limits"][0]["windows"][0]["window"] == "weekly"
    windows = {x["window"]: x for x in result["limits"][1]["windows"]}
    assert windows["five_hour"]["remainingPercent"] == 0
    assert windows["weekly"]["remainingPercent"] == 80
    assert "accountId" not in str(result)
    assert "secret" not in str(result)


def test_legacy_payload_and_malformed_window_are_supported():
    result = normalize_rate_limits({
        "rateLimits": {"limitId": "codex", "planType": "plus", "primary": {"usedPercent": 10, "windowDurationMins": "bad"}},
        "planType": "plus",
    })
    assert result["limits"] == []
    assert result["planType"] == "plus"


@pytest.mark.asyncio
async def test_service_caches_success_and_force_refreshes():
    class Client:
        def __init__(self): self.calls = 0
        async def read_rate_limits(self):
            self.calls += 1
            return {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": self.calls, "windowDurationMins": 300}}}
    client = Client()
    service = QuotaService(client=client, ttl=60, clock=lambda: 1)
    first = await service.get()
    second = await service.get()
    forced = await service.refresh()
    assert client.calls == 2
    assert first is second
    assert forced["limits"][0]["windows"][0]["usedPercent"] == 2


@pytest.mark.asyncio
async def test_service_keeps_last_good_snapshot_on_error():
    class Client:
        def __init__(self): self.fail = False
        async def read_rate_limits(self):
            if self.fail: raise CodexUsageError("timeout", "timed out")
            return {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": 1, "windowDurationMins": 300}}}
    client = Client()
    now = [0]
    service = QuotaService(client=client, ttl=1, clock=lambda: now[0])
    good = await service.get()
    now[0] = 2
    client.fail = True
    stale = await service.get()
    assert good["stale"] is False
    assert stale["stale"] is True
    assert stale["refreshError"]["code"] == "timeout"
