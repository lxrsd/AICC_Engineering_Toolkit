#!/usr/bin/env python3
"""CI check: framework integrity.

Verifies the committed evidence is internally consistent with the AICC
framework-version policy, WITHOUT reaching into any tool's private engine
state. Specifically:

  1. The evidence manifest's framework.version is a valid semver.
  2. That version satisfies the pinned support window declared in
     `docs/engineering-standard/framework-version.json` (the version policy's
     machine-readable companion): it is >= min_supported and <= max_supported,
     and not in the `blocked` list.
  3. The evidence contract schema and exporter the manifest depends on are
     present in the repository (so the evidence is reproducible from committed
     code).

This is a tool-independent check: it reads only committed files.

Usage:
    check_framework_integrity.py --manifest <manifest.json> --repo-root <dir>
                                 [--policy <framework-version.json>]
Exit 0 on pass, 1 on policy violation, 2 on IO/usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _semver_tuple(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a valid semver: {v!r}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AICC framework integrity check.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--policy", default=None)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.repo_root)
    policy_path = pathlib.Path(args.policy) if args.policy else (
        root / "docs" / "engineering-standard" / "framework-version.json"
    )

    try:
        manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []

    version = manifest.get("framework", {}).get("version", "")
    try:
        v = _semver_tuple(version)
    except ValueError as exc:
        print(f"FAIL: framework integrity: {exc}", file=sys.stderr)
        return 1

    try:
        lo = _semver_tuple(policy["min_supported"])
        hi = _semver_tuple(policy["max_supported"])
    except (KeyError, ValueError) as exc:
        print(f"ERROR: malformed version policy: {exc}", file=sys.stderr)
        return 2

    if v < lo:
        errors.append(f"framework version {version} is below min_supported {policy['min_supported']}")
    if v > hi:
        errors.append(f"framework version {version} is above max_supported {policy['max_supported']}")
    if version in policy.get("blocked", []):
        errors.append(f"framework version {version} is explicitly blocked by policy")

    # The schema + exporter the evidence depends on must be committed, so the
    # evidence is reproducible from code in this repo.
    for required in policy.get("required_framework_files", []):
        if not (root / required).is_file():
            errors.append(f"required framework file missing: {required}")

    if errors:
        print("FAIL: framework integrity", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"PASS: framework integrity (version {version} within "
          f"[{policy['min_supported']}, {policy['max_supported']}])")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
