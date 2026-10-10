#!/usr/bin/env python3
"""CI check: a manifest's tool.id is governed by the tool certification registry.

The evidence contract is OPEN: the schema accepts any kebab-case tool id, so
new AI coding environments can be added without changing the schema. Eligibility
and certification state are governed HERE, by the registry
(docs/engineering-standard/tool-registry.json), not by a hardcoded list.

Rules enforced:
  * The manifest's tool.id MUST be present in the registry.
  * The registry entry's `accept_evidence` MUST be true for CI to accept the
    manifest (i.e. the tool is CERTIFIED, or an explicitly evidence-accepting
    PENDING pilot). FAILED / UNSUPPORTED tools, or PENDING tools not yet
    accepting evidence, are rejected.
  * The manifest's framework.version MUST be >= the tool's min_framework_version.

This keeps governance tool-agnostic: adding a tool is a registry + adapter
change, never a code change to the schema, exporter, or this check.

Usage:
    check_tool_registry.py --manifest <manifest.json> [--registry <file>]
Exit 0 pass, 1 governance violation, 2 IO/usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


def _semver(v: str):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AICC tool-registry governance check.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--registry", default="docs/engineering-standard/tool-registry.json")
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
        registry = json.loads(pathlib.Path(args.registry).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    tool_id = manifest.get("tool", {}).get("id", "")
    version = manifest.get("framework", {}).get("version", "")
    by_id = {t["id"]: t for t in registry.get("tools", [])}

    errors: list[str] = []
    entry = by_id.get(tool_id)
    if entry is None:
        errors.append(f"tool id '{tool_id}' is not in the certification registry")
    else:
        if not entry.get("accept_evidence", False):
            errors.append(
                f"tool '{tool_id}' is state={entry.get('state')} and does not accept evidence "
                f"({entry.get('state_reason', '')})"
            )
        mv = _semver(entry.get("min_framework_version", ""))
        fv = _semver(version)
        if mv and fv and fv < mv:
            errors.append(
                f"framework version {version} is below tool '{tool_id}' minimum "
                f"{entry['min_framework_version']}"
            )

    if errors:
        print("FAIL: tool registry governance", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"PASS: tool registry governance (tool '{tool_id}' state={entry.get('state')}, accepts evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
