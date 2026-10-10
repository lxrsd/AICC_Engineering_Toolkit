#!/usr/bin/env python3
"""AICC Engineering Toolkit installer.

Sets up the AICC AI-DLC engineering standard for a supported AI coding tool in
the ENGINEER'S OWN project. It applies AICC-authored methodology, adapters,
templates, and validators, and drives the AI-DLC runtime through its
*authorized external* install mechanism (the `aidlc` CLI). It never bundles or
redistributes the third-party runtime.

Design rules:
  * No dependency on the private AICC_Unified repository.
  * Non-destructive: never overwrites an engineer's files without --force; writes
    adapter/template/validator copies into an AICC-namespaced subdir.
  * Idempotent where practical: re-running converges, reporting "already present".
  * Only CERTIFIED tools are offered as approved installation options; the public
    registry (capabilities/ai-dlc/validators/public-registry.json) is the source.
  * The AI-DLC runtime is obtained from its authorized source (`aidlc`), not from
    this package. If `aidlc` is absent, the installer reports how to obtain it and
    does NOT fabricate a download.

Stdlib only. Usage:
    installer/install.py --list
    installer/install.py --capability ai-dlc --tool kiro-cli --target <project-dir> [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

TOOLKIT_ROOT = pathlib.Path(__file__).resolve().parent.parent
AI_DLC = TOOLKIT_ROOT / "capabilities" / "ai-dlc"
PUBLIC_REGISTRY = AI_DLC / "validators" / "public-registry.json"

# Tools this installer can set up (must also be CERTIFIED in the public registry
# to be OFFERED as approved). Adapter dir -> runtime harness id.
TOOL_HARNESS = {"kiro-cli": "kiro", "claude-code": "claude"}


def load_registry() -> dict:
    return json.loads(PUBLIC_REGISTRY.read_text(encoding="utf-8"))


def certified_tools(reg: dict) -> dict[str, dict]:
    return {t["id"]: t for t in reg.get("tools", []) if t.get("certification_state") == "CERTIFIED"}


def detect_prereqs() -> dict[str, str | None]:
    def which(cmd: str) -> str | None:
        return shutil.which(cmd)
    return {
        "python3": sys.executable,
        "git": which("git"),
        "aidlc": which("aidlc"),        # the authorized AI-DLC runtime CLI
        "kiro-cli": which("kiro-cli"),
        "claude": which("claude"),
    }


def cmd_list() -> int:
    reg = load_registry()
    print(f"AICC Engineering Toolkit — framework AI-DLC {reg['tools'][0].get('framework_version','?')}")
    print("\nCapabilities:")
    print("  ai-dlc      — AI-Driven Development Life Cycle engineering standard")
    print("  factory-ai  — FUTURE placeholder (not installable)")
    print("\nAI-DLC tool options (only CERTIFIED tools are approved for install):")
    for t in reg.get("tools", []):
        state = t["certification_state"]
        q = f" ({t['qualification']})" if t.get("qualification") else ""
        approved = "APPROVED" if state == "CERTIFIED" and t["id"] in TOOL_HARNESS else "not an install option"
        print(f"  {t['id']:<12} {state}{q:<24} [{approved}]")
    return 0


def install(capability: str, tool: str, target: pathlib.Path, force: bool, dry_run: bool) -> int:
    if capability == "factory-ai":
        print("ERROR: factory-ai is a FUTURE placeholder and is not installable.", file=sys.stderr)
        return 2
    if capability != "ai-dlc":
        print(f"ERROR: unknown capability '{capability}'. Try --list.", file=sys.stderr)
        return 2

    reg = load_registry()
    certified = certified_tools(reg)
    if tool not in TOOL_HARNESS:
        print(f"ERROR: '{tool}' is not a supported install target. Supported: {', '.join(TOOL_HARNESS)}.", file=sys.stderr)
        return 2
    if tool not in certified:
        state = next((t["certification_state"] for t in reg["tools"] if t["id"] == tool), "UNKNOWN")
        print(f"ERROR: '{tool}' is {state}, not CERTIFIED. The installer only offers certified tools.", file=sys.stderr)
        return 2

    prereqs = detect_prereqs()
    print("== Prerequisites ==")
    for k, v in prereqs.items():
        print(f"  {k:<10} {'found: ' + v if v else 'NOT FOUND'}")

    missing_runtime = prereqs["aidlc"] is None
    if missing_runtime:
        print("\nNOTE: the AI-DLC runtime (`aidlc`) was not found on PATH.")
        print("The Toolkit does NOT bundle or redistribute the runtime. Obtain it from")
        print("its authorized source (your AI tool's AI-DLC runtime install), then re-run.")
        print("The adapter README documents the exact `aidlc config --harness <tool> --yes` step.")

    target.mkdir(parents=True, exist_ok=True)
    dest = target / ".aicc" / "ai-dlc"
    print(f"\n== Applying AICC AI-DLC standard to {target} ==")
    print(f"   (AICC-namespaced, non-destructive: writes under {dest.relative_to(target)}/)")

    to_copy = [
        (AI_DLC / "methodology", dest / "methodology"),
        (AI_DLC / "adapters" / tool, dest / "adapter"),
        (AI_DLC / "validators", dest / "validators"),
        (AI_DLC / "templates", dest / "templates"),
    ]
    for src, dst in to_copy:
        if not src.exists():
            print(f"   SKIP (source missing): {src}")
            continue
        if dst.exists() and not force:
            print(f"   already present: {dst.relative_to(target)}/ (use --force to refresh)")
            continue
        if dry_run:
            print(f"   DRY-RUN would copy {src.name} -> {dst.relative_to(target)}/")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"   installed: {dst.relative_to(target)}/")

    # Runtime adapter wiring — only if the authorized runtime is present.
    harness = TOOL_HARNESS[tool]
    ran_runtime = False
    if not missing_runtime and not dry_run:
        print(f"\n== Configuring the AI-DLC runtime for {tool} (authorized `aidlc` CLI) ==")
        try:
            r = subprocess.run(["aidlc", "config", "--harness", harness, "--yes"],
                               cwd=str(target), capture_output=True, text=True, timeout=120)
            print(r.stdout.strip()[:800] or "(no stdout)")
            ran_runtime = r.returncode == 0
            if r.returncode != 0:
                print(f"   aidlc config returned {r.returncode}: {r.stderr.strip()[:300]}", file=sys.stderr)
        except Exception as exc:
            print(f"   could not run `aidlc config`: {exc}", file=sys.stderr)

    # Post-install validation (Toolkit-local; never touches private repo).
    print("\n== Post-install validation ==")
    val = dest / "validators"
    results = {}
    if (val / "test_evidence.py").exists() and not dry_run:
        rv = subprocess.run([sys.executable, str(val / "test_evidence.py")],
                            capture_output=True, text=True, cwd=str(val))
        results["evidence_fixtures"] = "PASS" if rv.returncode == 0 else "FAIL"
    if (val / "public-registry.json").exists():
        results["public_registry"] = "present"

    print("\n== Install report ==")
    print(f"  Capability:        ai-dlc")
    print(f"  Tool:              {tool} (CERTIFIED{' — ' + certified[tool]['qualification'] if certified[tool].get('qualification') else ''})")
    print(f"  Framework version: {certified[tool].get('framework_version','?')}")
    print(f"  Runtime wired:     {'yes' if ran_runtime else 'no (install `aidlc` and re-run)'}")
    print(f"  Validation:        {results if results else '(dry-run or skipped)'}")
    print(f"  Target:            {target}")
    outstanding = [k for k, v in prereqs.items() if v is None and k in ('aidlc', tool.split('-')[0] if tool!='claude-code' else 'claude')]
    if outstanding:
        print(f"  Outstanding prereqs: {outstanding}")
    print("\n  This Toolkit requires NO access to the private AICC_Unified repository.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="AICC Engineering Toolkit installer.")
    ap.add_argument("--list", action="store_true", help="list capabilities and certified tools")
    ap.add_argument("--capability", default="ai-dlc")
    ap.add_argument("--tool", help="kiro-cli | claude-code")
    ap.add_argument("--target", default=".", help="engineer's project directory")
    ap.add_argument("--force", action="store_true", help="refresh already-installed files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.list or not args.tool:
        return cmd_list()
    return install(args.capability, args.tool, pathlib.Path(args.target).resolve(), args.force, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
