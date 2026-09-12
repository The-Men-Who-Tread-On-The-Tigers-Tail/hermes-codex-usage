import pytest

import dashboard.plugin_api as plugin_api


@pytest.mark.asyncio
async def test_quota_routes_delegate_to_shared_service(monkeypatch):
    calls = []

    class Service:
        async def get(self):
            calls.append("get")
            return {"success": True, "limits": []}

        async def refresh(self):
            calls.append("refresh")
            return {"success": True, "limits": [], "forced": True}

    monkeypatch.setattr(plugin_api, "_service", Service())
    assert await plugin_api.get_quota() == {"success": True, "limits": []}
    assert await plugin_api.refresh_quota() == {"success": True, "limits": [], "forced": True}
    assert calls == ["get", "refresh"]


def test_routes_are_read_only_or_explicit_refresh():
    assert {(route.path, frozenset(route.methods)) for route in plugin_api.router.routes} == {
        ("/quota", frozenset({"GET"})),
        ("/quota/refresh", frozenset({"POST"})),
    }
