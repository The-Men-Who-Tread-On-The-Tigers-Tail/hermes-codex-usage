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
    return await _service.get()


@router.post("/quota/refresh")
async def refresh_quota():
    return await _service.refresh()
