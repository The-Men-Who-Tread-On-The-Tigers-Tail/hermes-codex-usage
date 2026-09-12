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
    assert [(x["limitId"], x["window"]) for x in result["limits"]] == [
        ("codex", "weekly"),
        ("codex_bengalfox", "five_hour"),
        ("codex_bengalfox", "weekly"),
    ]
    windows = {(x["limitId"], x["window"]): x for x in result["limits"]}
    assert windows[("codex_bengalfox", "five_hour")]["remainingPercent"] == 0
    assert windows[("codex_bengalfox", "weekly")]["remainingPercent"] == 80
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
    assert forced["limits"][0]["usedPercent"] == 2


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


@pytest.mark.asyncio
async def test_service_deduplicates_concurrent_fetches():
    started = asyncio.Event()
    release = asyncio.Event()

    class Client:
        calls = 0

        async def read_rate_limits(self):
            self.calls += 1
            started.set()
            await release.wait()
            return {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": 2, "windowDurationMins": 300}}}

    client = Client()
    service = QuotaService(client=client, ttl=0)
    tasks = [asyncio.create_task(service.get(force=True)) for _ in range(3)]
    await started.wait()
    assert client.calls == 1
    release.set()
    results = await asyncio.gather(*tasks)
    assert results[0] == results[1] == results[2]


@pytest.mark.asyncio
async def test_service_backoffs_initial_failures():
    now = [0]

    class Client:
        calls = 0

        async def read_rate_limits(self):
            self.calls += 1
            raise CodexUsageError("timeout", "timed out")

    client = Client()
    service = QuotaService(client=client, failure_ttl=5, clock=lambda: now[0])
    first = await service.get()
    second = await service.get()
    assert first == second
    assert client.calls == 1
    now[0] = 6
    await service.get()
    assert client.calls == 2
