#!/usr/bin/env python3
"""CI check: required artifacts are present.

Reads the list of standard-mandated artifacts from
`docs/engineering-standard/required-artifacts.json` and verifies every one
exists in the repository. This guarantees the shared engineering standard's
deliverables are actually committed, independent of which AI tool produced
them.

Usage:
    check_required_artifacts.py --repo-root <dir> [--manifest <manifest.json>]

If --manifest is given, also verifies that every required artifact appears in
the manifest's artifact inventory (so the evidence manifest is complete).

Exit 0 on pass, 1 on a missing artifact, 2 on IO/usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AICC required-artifacts check.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--required", default=None)
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.repo_root)
    required_path = pathlib.Path(args.required) if args.required else (
        root / "docs" / "engineering-standard" / "required-artifacts.json"
    )

    try:
        required = json.loads(required_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read required-artifacts list: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    required_paths = required.get("required", [])
    for rel in required_paths:
        if not (root / rel).is_file():
            errors.append(f"required artifact missing from repository: {rel}")

    if args.manifest:
        try:
            manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read manifest: {exc}", file=sys.stderr)
            return 2
        in_manifest = {a.get("path") for a in manifest.get("artifacts", [])}
        for rel in required.get("must_appear_in_manifest", []):
            if rel not in in_manifest:
                errors.append(f"required artifact not listed in evidence manifest: {rel}")

    if errors:
        print("FAIL: required artifacts", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"PASS: required artifacts ({len(required_paths)} present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
