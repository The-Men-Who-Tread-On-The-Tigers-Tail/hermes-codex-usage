"""FastAPI routes for the Hermes Codex usage desktop plugin."""
from __future__ import annotations

from pathlib import Path
import sys

from fastapi import APIRouter

# Hermes loads this file as a standalone module rather than as a package.
_dashboard_dir = str(Path(__file__).resolve().parent)
if _dashboard_dir not in sys.path:
    sys.path.insert(0, _dashboard_dir)

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
