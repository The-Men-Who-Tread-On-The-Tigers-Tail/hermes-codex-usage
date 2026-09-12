"""Minimal, credential-blind JSON-RPC client for Codex app-server."""
from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any, Dict, Optional


class CodexUsageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CodexAppServerClient:
    def __init__(self, executable: str = "codex", timeout: float = 10.0) -> None:
        self.executable = executable
        self.timeout = timeout

    async def read_rate_limits(self) -> Dict[str, Any]:
        executable = shutil.which(self.executable)
        if executable is None:
            raise CodexUsageError("codex_not_found", "Codex CLI was not found on PATH.")
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                executable, "app-server", "--stdio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._send(process, {
                "id": "hermes-init",
                "method": "initialize",
                "params": {"clientInfo": {"name": "hermes-codex-usage", "title": "Hermes Codex Usage", "version": "0.1.0"}},
            })
            await self._read_response(process, "hermes-init")
            await self._send(process, {"method": "initialized", "params": {}})
            await self._send(process, {"id": "hermes-rate-limits", "method": "account/rateLimits/read", "params": {}})
            response = await self._read_response(process, "hermes-rate-limits")
            result = response.get("result")
            if not isinstance(result, dict):
                raise CodexUsageError("invalid_response", "Codex returned no rate-limit data.")
            return result
        except CodexUsageError:
            raise
        except asyncio.TimeoutError:
            raise CodexUsageError("timeout", "Codex did not return usage data in time.")
        except (BrokenPipeError, ConnectionError, OSError):
            raise CodexUsageError("codex_process_error", "The Codex app-server process ended unexpectedly.")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CodexUsageError("invalid_response", "Codex returned invalid usage data.")
        finally:
            if process is not None:
                if process.returncode is None:
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    async def _send(self, process: asyncio.subprocess.Process, message: Dict[str, Any]) -> None:
        if process.stdin is None:
            raise CodexUsageError("codex_process_error", "Codex app-server stdin is unavailable.")
        process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
        await process.stdin.drain()

    async def _read_response(self, process: asyncio.subprocess.Process, request_id: str) -> Dict[str, Any]:
        if process.stdout is None:
            raise CodexUsageError("codex_process_error", "Codex app-server stdout is unavailable.")
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=self.timeout)
            if not line:
                raise CodexUsageError("codex_process_error", "The Codex app-server process ended unexpectedly.")
            if len(line) > 1024 * 1024:
                raise CodexUsageError("invalid_response", "Codex returned an oversized usage message.")
            try:
                message = json.loads(line.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise CodexUsageError("invalid_response", "Codex returned invalid usage data.")
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexUsageError("rpc_error", "Codex rejected the usage request.")
            return message
