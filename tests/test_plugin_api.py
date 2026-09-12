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




@pytest.mark.asyncio
async def test_routes_sanitize_unexpected_service_errors(monkeypatch):
    class BrokenService:
        async def get(self):
            raise RuntimeError("token=secret accountId=private")

        async def refresh(self):
            raise RuntimeError("raw backend details")

    monkeypatch.setattr(plugin_api, "_service", BrokenService())
    read_error = await plugin_api.get_quota()
    refresh_error = await plugin_api.refresh_quota()
    assert read_error["error"] == {"code": "internal_error", "message": "Codex usage could not be read."}
    assert refresh_error["error"] == {"code": "internal_error", "message": "Codex usage could not be refreshed."}
    assert "secret" not in str(read_error)
    assert "private" not in str(read_error)
    assert "raw backend" not in str(refresh_error)
