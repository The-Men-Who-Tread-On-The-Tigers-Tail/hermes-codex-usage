"""FastAPI routes for the Hermes Codex usage desktop plugin."""
from __future__ import annotations

from fastapi import APIRouter

try:
    from .quota import QuotaService
except ImportError:  # Hermes may load dashboard modules as top-level files.
    from quota import QuotaService


router = APIRouter()
_service = QuotaService()


@router.get("/quota")
async def get_quota():
    try:
        return await _service.get()
    except Exception:
        return {
            "success": False,
            "source": "codex-app-server",
            "fetchedAt": None,
            "stale": False,
            "error": {"code": "internal_error", "message": "Codex usage could not be read."},
            "limits": [],
        }


@router.post("/quota/refresh")
async def refresh_quota():
    try:
        return await _service.refresh()
    except Exception:
        return {
            "success": False,
            "source": "codex-app-server",
            "fetchedAt": None,
            "stale": False,
            "error": {"code": "internal_error", "message": "Codex usage could not be refreshed."},
            "limits": [],
        }
