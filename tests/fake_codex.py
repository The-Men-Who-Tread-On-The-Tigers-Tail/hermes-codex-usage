#!/usr/bin/env python3
"""Deterministic fake Codex app-server for credential-free tests."""
import json
import os
import sys
from pathlib import Path

MODE = os.environ.get("FAKE_CODEX_MODE", "success")
FIXTURES = Path(__file__).parent / "fixtures"

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        print(json.dumps({"id": message["id"], "result": {"ok": True}}), flush=True)
        continue
    if method != "account/rateLimits/read":
        continue
    if MODE == "timeout":
        sys.stdout.flush()
        continue
    if MODE == "early_exit":
        raise SystemExit(0)
    if MODE == "malformed_json":
        print("not-json", flush=True)
        continue
    if MODE == "stderr_noise":
        print("synthetic stderr noise", file=sys.stderr, flush=True)
    if MODE == "rpc_auth_error":
        print(json.dumps({"id": message["id"], "error": {"code": "authentication_required"}}), flush=True)
        continue
    if MODE == "rpc_error":
        print(json.dumps({"id": message["id"], "error": {"code": "provider_error"}}), flush=True)
        continue
    for notification in FIXTURES.joinpath("rpc_notifications.jsonl").read_text().splitlines():
        print(notification, flush=True)
    payload = json.loads(FIXTURES.joinpath("rate_limits_multi.json").read_text())
    print(json.dumps({"id": message["id"], "result": payload}), flush=True)
