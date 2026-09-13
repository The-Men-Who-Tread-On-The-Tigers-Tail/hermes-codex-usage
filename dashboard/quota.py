"""Normalization and cached service for Codex account rate limits."""
from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    from .codex_rpc import CodexAppServerClient, CodexUsageError
except ImportError:  # Hermes may load dashboard modules as top-level files.
    from codex_rpc import CodexAppServerClient, CodexUsageError



def _window_name(minutes: Any) -> Optional[str]:
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return None
    if value == 300:
        return "five_hour"
    if value == 10080:
        return "weekly"
    return "custom" if value > 0 else None


def _parse_finite_number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clean_credits(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    result: Dict[str, Any] = {}
    for key in ("hasCredits", "unlimited"):
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    if value.get("balance") is not None:
        result["balance"] = str(value["balance"])
    return result or None


def normalize_rate_limits(payload: Dict[str, Any], fetched_at: Optional[str] = None) -> Dict[str, Any]:
    """Return a privacy-safe, deterministic subset of a Codex response."""
    if not isinstance(payload, dict):
        raise ValueError("rate-limit response must be an object")
    by_id = payload.get("rateLimitsByLimitId")
    entries: List[tuple[str, Dict[str, Any]]] = []
    if isinstance(by_id, dict):
        entries = [(str(key), value) for key, value in by_id.items() if isinstance(value, dict)]
    elif isinstance(payload.get("rateLimits"), dict):
        rate = payload["rateLimits"]
        entries = [(str(rate.get("limitId") or "codex"), rate)]

    limits: List[Dict[str, Any]] = []
    for limit_id, item in entries:
        windows: List[Dict[str, Any]] = []
        for field in ("primary", "secondary"):
            window = item.get(field)
            if not isinstance(window, dict):
                continue
            duration = window.get("windowDurationMins")
            name = _window_name(duration)
            used = _parse_finite_number(window.get("usedPercent"))
            try:
                duration_int = int(duration)
            except (TypeError, ValueError):
                duration_int = None
            if name is None or used is None or duration_int is None:
                continue
            limits.append({
                "limitId": limit_id,
                "limitName": item.get("limitName") if isinstance(item.get("limitName"), str) else None,
                "window": name,
                "windowDurationMins": duration_int,
                "usedPercent": used,
                "remainingPercent": max(0.0, min(100.0, 100.0 - used)),
                "resetsAt": window.get("resetsAt") if isinstance(window.get("resetsAt"), (int, float)) else None,
            })

    limits.sort(key=lambda item: (
        0 if item["limitId"] == "codex" else 1,
        item["limitId"],
        item["windowDurationMins"],
        item["window"],
    ))
    result: Dict[str, Any] = {
        "success": True,
        "source": "codex-app-server",
        "fetchedAt": fetched_at or datetime.now(timezone.utc).isoformat(),
        "stale": False,
        "planType": payload.get("planType") if isinstance(payload.get("planType"), str) else None,
        "ordinaryUsageAllowed": payload.get("ordinaryUsageAllowed") if isinstance(payload.get("ordinaryUsageAllowed"), bool) else None,
        "credits": _clean_credits(payload.get("credits")),
        "limits": limits,
    }
    return result


class QuotaService:
    def __init__(self, client: Optional[CodexAppServerClient] = None, ttl: float = 15 * 60.0, failure_ttl: float = 5.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.client = client or CodexAppServerClient()
        self.ttl = ttl
        self.failure_ttl = failure_ttl
        self.clock = clock
        self._snapshot: Optional[Dict[str, Any]] = None
        self._cached_at = 0.0
        self._failure_result: Optional[Dict[str, Any]] = None
        self._failure_cached_at = 0.0
        self._inflight: Optional[asyncio.Task] = None

    async def get(self, force: bool = False) -> Dict[str, Any]:
        now = self.clock()
        if not force and self._snapshot is not None and now - self._cached_at < self.ttl:
            return self._snapshot
        if not force and self._failure_result is not None and now - self._failure_cached_at < self.failure_ttl:
            return self._failure_result
        if self._inflight is None:
            self._inflight = asyncio.create_task(self._fetch())
            self._inflight.add_done_callback(self._clear_inflight)
        return await asyncio.shield(self._inflight)

    def _clear_inflight(self, task: asyncio.Task) -> None:
        if self._inflight is task:
            self._inflight = None

    async def _fetch(self) -> Dict[str, Any]:
        try:
            payload = await self.client.read_rate_limits()
            snapshot = normalize_rate_limits(payload)
        except CodexUsageError as exc:
            if self._snapshot is not None:
                result = dict(self._snapshot)
                result["stale"] = True
                result["refreshError"] = {"code": exc.code, "message": str(exc)}
            else:
                result = {"success": False, "source": "codex-app-server", "fetchedAt": None, "stale": False,
                          "error": {"code": exc.code, "message": str(exc)}, "limits": []}
            self._failure_result = result
            self._failure_cached_at = self.clock()
            return result
        self._snapshot = snapshot
        self._cached_at = self.clock()
        self._failure_result = None
        return snapshot

    async def refresh(self) -> Dict[str, Any]:
        return await self.get(force=True)
