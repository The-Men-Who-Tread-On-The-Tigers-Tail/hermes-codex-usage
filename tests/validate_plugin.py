#!/usr/bin/env python3
"""Portable CI validation for the plugin package layout."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "dashboard/manifest.json").read_text())
yaml_lines = (ROOT / "plugin.yaml").read_text().splitlines()
yaml = dict(line.split(":", 1) for line in yaml_lines if ":" in line)

required = ["__init__.py", "plugin.yaml", "dashboard/manifest.json", "dashboard/plugin_api.py", "desktop/plugin.js"]
missing = [path for path in required if not (ROOT / path).is_file()]
if missing:
    raise SystemExit(f"missing plugin files: {missing}")

if yaml.get("name", "").strip() != manifest.get("name"):
    raise SystemExit("plugin name mismatch")
if yaml.get("version", "").strip() != manifest.get("version"):
    raise SystemExit("plugin version mismatch")

module = ast.parse((ROOT / "__init__.py").read_text())
registers = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "register"]
if not registers or len(registers[0].args.args) != 1:
    raise SystemExit("__init__.py must define register(ctx)")

print("portable plugin validation passed")
