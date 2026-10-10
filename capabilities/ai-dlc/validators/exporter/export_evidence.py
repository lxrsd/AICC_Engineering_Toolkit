#!/usr/bin/env python3
"""Export a tool-independent AICC AI-DLC evidence manifest.

Stdlib-only. The exporter is deliberately tool-AGNOSTIC: it consumes a small,
neutral "run descriptor" (JSON) that each tool's SEPARATE onboarding adapter
produces, and emits a manifest that conforms to
`engineering-hub/evidence/schema/evidence-manifest.schema.json`.

Design rules (from the evidence contract):
  * The exporter never reads a tool's private engine state. Adapters do the
    tool-specific mapping and hand this exporter only neutral facts.
  * The exporter never fabricates or claims verified human approvals. If a run
    descriptor declares approval gates, they are copied into the OPTIONAL
    `approvals` block with `verifiable_by_ci: false`, encoding that CI cannot
    verify them.
  * Artifact hashes are computed from the committed files on disk, so the
    manifest is content-addressed and CI can re-verify it.

Run descriptor shape (neutral, tool-agnostic) -- see the adapters under
`docs/engineering-standard/onboarding/adapters/` for how each tool produces it:

{
  "tool": {"id": "kiro-cli", "surface": "Kiro CLI 2.x", "adapter_version": "1.0.0"},
  "framework": {"name": "AI-DLC", "version": "2.10.0", "scope": "aicc-engineering-standard"},
  "intent": {"id": "261008-multi-ide-standard", "title": "...", "guard_policy": "strict"},
  "stages": [{"slug": "intent-capture", "phase": "ideation", "status": "completed",
              "produced_artifacts": ["docs/..."]}],
  "tests": {"framework": "python-unittest", "total": 6, "passed": 6, "failed": 0,
            "results_path": "engineering-hub/evidence/exporter/.last-test-results.json"},
  "artifacts": [{"path": "docs/engineering-standard/01-governance-policy.md", "kind": "governance"}],
  "declared_approvals": [{"stage": "intent-capture", "declared_outcome": "approved"}]
}

Usage:
    export_evidence.py --descriptor <run-descriptor.json> --repo-root <dir> --out <manifest.json>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import sys

SCHEMA_VERSION = "1.0.0"


def sha256_of(file_path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(descriptor: dict, repo_root: pathlib.Path) -> dict:
    root = repo_root.resolve()

    artifacts = []
    for art in descriptor.get("artifacts", []):
        rel = art["path"]
        target = (root / rel).resolve()
        target.relative_to(root)  # raises ValueError if the path escapes the repo
        if not target.is_file():
            raise FileNotFoundError(f"artifact not found: {rel}")
        artifacts.append({
            "path": rel,
            "sha256": sha256_of(target),
            "kind": art.get("kind", "other"),
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": descriptor["tool"],
        "framework": descriptor["framework"],
        "intent": descriptor["intent"],
        "stages": descriptor.get("stages", []),
        "tests": descriptor["tests"],
        "artifacts": artifacts,
    }

    declared = descriptor.get("declared_approvals")
    if declared:
        # Honesty rule: declared, NOT verified. verifiable_by_ci is always false.
        manifest["approvals"] = {
            "verifiable_by_ci": False,
            "declared_gates": [
                {"stage": g["stage"], "declared_outcome": g["declared_outcome"]}
                for g in declared
            ],
        }

    return manifest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export an AICC AI-DLC evidence manifest.")
    parser.add_argument("--descriptor", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        descriptor = json.loads(pathlib.Path(args.descriptor).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read descriptor {args.descriptor}: {exc}", file=sys.stderr)
        return 2

    try:
        manifest = build_manifest(descriptor, pathlib.Path(args.repo_root))
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: cannot build manifest: {exc}", file=sys.stderr)
        return 2

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE: {args.out} ({len(manifest['artifacts'])} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
