#!/usr/bin/env python3
"""CI check: sensitive files are excluded from the committed tree.

Fails if any tracked file matches a sensitive pattern. This protects against
three classes of leak the standard forbids in committed evidence:

  1. Secrets / credentials (.env, *.pem, id_rsa, AWS keys, generic *secret*).
  2. Private AI-DLC engine state (per-clone cursors, session tokens, framework
     runtime state) that is per-user/per-machine and must never be shared.
  3. Machine-specific or local-only artifacts (.DS_Store, *.local, caches).

It scans the set of git-tracked files when run inside a git work tree
(authoritative for "what is committed"); otherwise it walks the repo root
excluding common vendored directories. Patterns are declared in
`docs/engineering-standard/sensitive-file-patterns.json` so the policy is
auditable and testable.

Usage:
    check_sensitive_files.py --repo-root <dir> [--patterns <file>]
                             [--extra-root <dir> ...]

Exit 0 if clean, 1 if any sensitive file is present, 2 on IO/usage error.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import re
import subprocess
import sys


def tracked_files(root: pathlib.Path) -> list[str] | None:
    """Return git-tracked paths relative to root, or None if not a git tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [line for line in out.stdout.splitlines() if line.strip()]


def walked_files(root: pathlib.Path, skip_dirs: set[str]) -> list[str]:
    results: list[str] = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root)
            if any(part in skip_dirs for part in rel.parts):
                continue
            results.append(str(rel))
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AICC sensitive-file exclusion check.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--patterns", default=None)
    parser.add_argument("--extra-root", action="append", default=[],
                        help="additional directory to scan with the same patterns (used by tests)")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.repo_root)
    patterns_path = pathlib.Path(args.patterns) if args.patterns else (
        root / "docs" / "engineering-standard" / "sensitive-file-patterns.json"
    )

    try:
        policy = json.loads(patterns_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read sensitive-file patterns: {exc}", file=sys.stderr)
        return 2

    glob_patterns: list[str] = policy.get("glob_patterns", [])
    regex_patterns: list[re.Pattern] = [re.compile(p) for p in policy.get("regex_patterns", [])]
    content_patterns: list[re.Pattern] = [re.compile(p) for p in policy.get("content_regex_patterns", [])]
    content_max = int(policy.get("content_scan_max_bytes", 1048576))
    content_skip = tuple(policy.get("content_scan_skip_suffixes", []))
    skip_dirs: set[str] = set(policy.get("skip_dirs", [".git", "node_modules", "dist", "build"]))

    scan_targets: list[tuple[pathlib.Path, list[str]]] = []
    files = tracked_files(root)
    if files is None:
        files = walked_files(root, skip_dirs)
    scan_targets.append((root, files))
    for extra in args.extra_root:
        er = pathlib.Path(extra)
        scan_targets.append((er, walked_files(er, skip_dirs)))

    violations: list[str] = []
    for base, file_list in scan_targets:
        for rel in file_list:
            name = pathlib.PurePosixPath(rel).name
            flagged = False
            for gp in glob_patterns:
                if fnmatch.fnmatch(rel, gp) or fnmatch.fnmatch(name, gp):
                    violations.append(f"{base}/{rel} matches sensitive glob '{gp}'")
                    flagged = True
                    break
            if not flagged:
                for rp in regex_patterns:
                    if rp.search(rel):
                        violations.append(f"{base}/{rel} matches sensitive path pattern '{rp.pattern}'")
                        flagged = True
                        break
            if not flagged and content_patterns and not rel.endswith(content_skip):
                target = base / rel
                try:
                    if target.is_file() and target.stat().st_size <= content_max:
                        text = target.read_text(encoding="utf-8", errors="ignore")
                        for cp in content_patterns:
                            if cp.search(text):
                                violations.append(f"{base}/{rel} contains sensitive content matching '{cp.pattern}'")
                                break
                except OSError:
                    pass

    if violations:
        print("FAIL: sensitive files present in committed tree", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    total = sum(len(f) for _, f in scan_targets)
    print(f"PASS: sensitive-file exclusions ({total} files scanned, 0 sensitive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
