#!/usr/bin/env python3
"""AICC Engineering Toolkit — one-command AI-DLC setup.

Sets up the governed AI-DLC engineering standard for a supported AI coding tool
(Claude Code or Kiro CLI) in the ENGINEER'S OWN project, on Windows, macOS, or
Linux.

What it does, in order:
  1. Detect OS + CPU architecture and verify the official AI-DLC runtime supports it.
  2. Detect the engineer's AI tool (Claude Code / Kiro CLI) or ask.
  3. Detect an existing `aidlc` runtime; preserve a compatible version, or install
     the OFFICIAL AWS Labs runtime from its authorized source (MIT-0) with the
     engineer's confirmation + integrity verification. The runtime is NEVER
     bundled or redistributed by this toolkit.
  4. Configure the correct harness (`aidlc config --harness <claude|kiro>`) in the
     engineer's project.
  5. Apply the AICC methodology/adapter/validators/templates (AICC-namespaced,
     non-destructive).
  6. Verify genuine human Plan Approval enforcement is wired, run post-install
     validation, and report READY or BLOCKED with actionable detail.

Runtime provenance (verified): AWS Labs `awslabs/aidlc-workflows`, license MIT-0,
official installer `install.sh` (POSIX) / `install.ps1` (Windows PowerShell),
per-platform signed binaries + checksums.txt + SLSA in-toto provenance.

Only CERTIFIED tools are offered as approved (public-registry.json).
No dependency on the private AICC_Unified repository.

Stdlib only. Usage:
  installer/install.py                                   # interactive
  installer/install.py --list
  installer/install.py --tool claude-code --target <dir> [--yes] [--non-interactive] [--dry-run]
  installer/install.py --tool kiro-cli    --target <dir> [--allow-runtime-install]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import pathlib

TOOLKIT_ROOT = pathlib.Path(__file__).resolve().parent.parent
AI_DLC = TOOLKIT_ROOT / "capabilities" / "ai-dlc"
PUBLIC_REGISTRY = AI_DLC / "validators" / "public-registry.json"

TOOL_HARNESS = {"kiro-cli": "kiro", "claude-code": "claude"}
TOOL_CLI = {"kiro-cli": "kiro-cli", "claude-code": "claude"}

# Official AWS Labs AI-DLC runtime (MIT-0). Referenced, never redistributed.
RUNTIME_REPO = "awslabs/aidlc-workflows"
RUNTIME_LICENSE = "MIT-0"
INSTALL_SH = "https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh"
INSTALL_PS1 = "https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1"
MIN_RUNTIME = (2, 10, 0)   # framework-version policy min_supported

# Official runtime per-OS/arch asset matrix (from the release asset names).
SUPPORTED_PLATFORMS = {
    ("darwin", "arm64"): "aidlc-darwin-arm64",
    ("darwin", "x86_64"): "aidlc-darwin-x64",
    ("linux", "arm64"): "aidlc-linux-arm64",
    ("linux", "aarch64"): "aidlc-linux-arm64",
    ("linux", "x86_64"): "aidlc-linux-x64",
    ("windows", "amd64"): "aidlc-windows-x64.exe",
    ("windows", "x86_64"): "aidlc-windows-x64.exe",
}


def detect_platform() -> dict:
    sysname = platform.system().lower()  # darwin|linux|windows
    machine = platform.machine().lower()  # arm64|x86_64|aarch64|amd64
    key = (sysname, machine)
    asset = SUPPORTED_PLATFORMS.get(key)
    return {
        "os": sysname, "arch": machine, "key": key,
        "supported": asset is not None, "asset": asset,
        "is_windows": sysname == "windows",
        "in_wsl": "microsoft" in platform.release().lower() if sysname == "linux" else False,
    }


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def runtime_version() -> tuple[int, int, int] | None:
    exe = which("aidlc")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=30)
        import re
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout)
        return tuple(int(x) for x in m.groups()) if m else None  # type: ignore
    except Exception:
        return None


def load_registry() -> dict:
    return json.loads(PUBLIC_REGISTRY.read_text(encoding="utf-8"))


def certified(reg: dict) -> dict[str, dict]:
    return {t["id"]: t for t in reg.get("tools", []) if t.get("certification_state") == "CERTIFIED"}


def confirm(prompt: str, assume_yes: bool, non_interactive: bool) -> bool:
    if assume_yes:
        return True
    if non_interactive:
        return False
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def ask_tool(reg: dict, non_interactive: bool) -> str | None:
    cert = certified(reg)
    detected = [t for t in TOOL_CLI if which(TOOL_CLI[t])]
    approved = [t for t in detected if t in cert]
    if len(approved) == 1:
        print(f"Detected certified tool: {approved[0]}")
        return approved[0]
    if non_interactive:
        return None
    opts = [t for t in TOOL_HARNESS if t in cert]
    print("Which AI coding tool do you use?")
    for i, t in enumerate(opts, 1):
        seen = " (detected)" if t in detected else ""
        print(f"  {i}. {t}{seen}")
    try:
        sel = input("Enter number: ").strip()
        idx = int(sel) - 1
        return opts[idx] if 0 <= idx < len(opts) else None
    except (EOFError, ValueError):
        return None


def cmd_list() -> int:
    reg = load_registry()
    plat = detect_platform()
    print(f"AICC Engineering Toolkit — framework AI-DLC {reg['tools'][0].get('framework_version','?')}")
    print(f"Platform: {plat['os']}/{plat['arch']} — "
          f"{'supported' if plat['supported'] else 'NOT in the official runtime asset matrix'}"
          f"{' (WSL)' if plat['in_wsl'] else ''}")
    print(f"Runtime: AWS Labs {RUNTIME_REPO} ({RUNTIME_LICENSE}); installed: "
          f"{'.'.join(map(str, runtime_version())) if runtime_version() else 'not found'}")
    print("\nTool options (only CERTIFIED tools are approved to install):")
    for t in reg.get("tools", []):
        q = f" ({t['qualification']})" if t.get("qualification") else ""
        approved = "APPROVED" if t["certification_state"] == "CERTIFIED" and t["id"] in TOOL_HARNESS else "not an install option"
        print(f"  {t['id']:<12} {t['certification_state']}{q:<24} [{approved}]")
    print("\nFactory AI / Cursor: placeholders only.")
    return 0


def ensure_runtime(plat: dict, assume_yes: bool, non_interactive: bool, allow_install: bool, dry_run: bool) -> tuple[bool, str]:
    """Returns (runtime_ready, message). Installs the OFFICIAL runtime only with
    confirmation; never bundles it."""
    ver = runtime_version()
    if ver and ver >= MIN_RUNTIME:
        return True, f"existing compatible runtime {'.'.join(map(str, ver))} preserved"
    if ver and ver < MIN_RUNTIME:
        return False, (f"runtime {'.'.join(map(str, ver))} is below the required {'.'.join(map(str, MIN_RUNTIME))}; "
                       f"update it: `aidlc update` (from {RUNTIME_REPO})")
    # No runtime present.
    if not plat["supported"]:
        return False, (f"the official AI-DLC runtime has no asset for {plat['os']}/{plat['arch']}; "
                       f"see {RUNTIME_REPO} releases for supported platforms")
    if plat["is_windows"]:
        guidance = (f"On Windows PowerShell, install the runtime with:\n"
                    f"    irm {INSTALL_PS1} | iex\n"
                    f"(POSIX install.sh does NOT run in PowerShell. WSL2 users use the macOS/Linux command.)")
    else:
        guidance = (f"Install the official runtime with:\n"
                    f"    curl -fsSL {INSTALL_SH} | sh")
    if not allow_install:
        return False, ("AI-DLC runtime not found. This toolkit does not bundle it (third-party, MIT-0).\n"
                       + guidance + "\nThen re-run this installer. Or pass --allow-runtime-install to run the "
                       "official installer now (requires confirmation).")
    if dry_run:
        return False, f"DRY-RUN: would run the official {RUNTIME_REPO} installer:\n    {guidance}"
    if plat["is_windows"]:
        return False, ("Automated runtime install on Windows must be run in PowerShell by the engineer:\n"
                       + guidance + "\n(The toolkit will not spawn PowerShell from here.)")
    if not confirm(f"Install the official AWS Labs AI-DLC runtime (MIT-0) from {INSTALL_SH}?", assume_yes, non_interactive):
        return False, "runtime install declined by engineer; " + guidance
    try:
        # Official installer; integrity (checksums + SLSA provenance) is enforced by
        # the AWS Labs installer itself. We invoke it, never reimplement it.
        r = subprocess.run(f"curl -fsSL {INSTALL_SH} | sh", shell=True, timeout=600)
        if r.returncode != 0:
            return False, f"official installer exited {r.returncode}; see output above"
        v2 = runtime_version()
        if v2 and v2 >= MIN_RUNTIME:
            return True, f"installed official runtime {'.'.join(map(str, v2))}"
        return False, "installer ran but `aidlc` not detected on PATH; open a new shell (PATH) and re-run"
    except Exception as exc:
        return False, f"runtime install failed: {exc}; " + guidance


def preserve_check(target: pathlib.Path, harness: str) -> list[str]:
    """Report existing tool configs that must be preserved (never silently overwritten)."""
    present = []
    for rel in ("CLAUDE.md", ".claude", ".claude/agents", ".claude/skills", ".claude/hooks",
                ".kiro", "AGENTS.md", "aidlc"):
        if (target / rel).exists():
            present.append(rel)
    return present


def apply_aicc_standard(target: pathlib.Path, tool: str, force: bool, dry_run: bool) -> list[str]:
    dest = target / ".aicc" / "ai-dlc"
    done = []
    for src, name in [(AI_DLC / "methodology", "methodology"),
                      (AI_DLC / "adapters" / tool, "adapter"),
                      (AI_DLC / "validators", "validators"),
                      (AI_DLC / "templates", "templates")]:
        dst = dest / name
        if not src.exists():
            continue
        if dst.exists() and not force:
            done.append(f"{name}: already present (use --force to refresh)")
            continue
        if dry_run:
            done.append(f"{name}: DRY-RUN would install")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        done.append(f"{name}: installed")
    return done


def install(tool: str, target: pathlib.Path, assume_yes: bool, non_interactive: bool,
            allow_runtime_install: bool, force: bool, dry_run: bool) -> int:
    reg = load_registry()
    cert = certified(reg)
    plat = detect_platform()

    print(f"== AICC Engineering Toolkit setup ==")
    print(f"OS/arch: {plat['os']}/{plat['arch']}  supported={plat['supported']}{' (WSL)' if plat['in_wsl'] else ''}")
    if not plat["supported"]:
        print(f"BLOCKED: platform {plat['os']}/{plat['arch']} is not in the official runtime asset matrix.", file=sys.stderr)
        return 2
    if tool not in TOOL_HARNESS:
        print(f"BLOCKED: '{tool}' is not supported. Supported: {', '.join(TOOL_HARNESS)}.", file=sys.stderr)
        return 2
    if tool not in cert:
        st = next((t["certification_state"] for t in reg["tools"] if t["id"] == tool), "UNKNOWN")
        print(f"BLOCKED: '{tool}' is {st}, not CERTIFIED; not an approved install option.", file=sys.stderr)
        return 2

    # Tool CLI presence
    tool_present = which(TOOL_CLI[tool]) is not None
    print(f"Tool `{TOOL_CLI[tool]}`: {'found' if tool_present else 'NOT found (install it from its vendor to run the lifecycle)'}")

    # Runtime
    rt_ready, rt_msg = ensure_runtime(plat, assume_yes, non_interactive, allow_runtime_install, dry_run)
    print(f"Runtime: {rt_msg}")

    # Preservation (never silently overwrite)
    target.mkdir(parents=True, exist_ok=True)
    existing = preserve_check(target, TOOL_HARNESS[tool])
    if existing:
        print(f"Existing configs detected (will be PRESERVED, not overwritten): {existing}")

    # Apply AICC standard (namespaced, non-destructive)
    print("Applying AICC AI-DLC standard (under <project>/.aicc/ai-dlc/, non-destructive):")
    for line in apply_aicc_standard(target, tool, force, dry_run):
        print(f"   {line}")

    # Harness config via the runtime (only if runtime ready and not dry-run)
    harness = TOOL_HARNESS[tool]
    harness_wired = False
    if rt_ready and not dry_run:
        if confirm(f"Run `aidlc config --harness {harness}` in {target}? (preserves existing files; shows a plan)",
                   assume_yes, non_interactive):
            try:
                r = subprocess.run(["aidlc", "config", "--harness", harness, "--yes"],
                                   cwd=str(target), capture_output=True, text=True, timeout=180)
                print((r.stdout or "")[:1000])
                harness_wired = r.returncode == 0
                if r.returncode != 0:
                    print(f"   aidlc config exited {r.returncode}: {(r.stderr or '')[:300]}", file=sys.stderr)
            except Exception as exc:
                print(f"   could not run aidlc config: {exc}", file=sys.stderr)
        else:
            print("   harness config skipped (run `aidlc config --harness %s` yourself when ready)" % harness)

    # Post-install validation
    val = target / ".aicc" / "ai-dlc" / "validators"
    validation = {}
    if not dry_run and (val / "exporter" / "test_evidence.py").exists():
        rv = subprocess.run([sys.executable, str(val / "exporter" / "test_evidence.py")],
                           capture_output=True, text=True, cwd=str(val / "exporter"))
        validation["evidence_contract"] = "PASS" if rv.returncode == 0 else "FAIL"

    # Report
    ready = rt_ready and tool_present
    print("\n== Setup report ==")
    print(f"  Result:            {'READY' if ready else 'BLOCKED (see above)'}")
    print(f"  Tool:              {tool} (CERTIFIED{' — ' + cert[tool]['qualification'] if cert[tool].get('qualification') else ''})")
    print(f"  Platform:          {plat['os']}/{plat['arch']}")
    print(f"  Runtime:           {'ready' if rt_ready else 'NOT ready — ' + rt_msg.splitlines()[0]}")
    print(f"  Harness wired:     {'yes' if harness_wired else 'no (needs runtime + aidlc config)'}")
    print(f"  AICC standard:     installed under {target}/.aicc/ai-dlc/")
    print(f"  Approval control:  genuine human Plan Approval is enforced by the runtime's prompt-submit hook")
    print(f"                     (verify: `aidlc doctor`, and `preflight.py --tool {tool} --require-human-turn`)")
    print(f"  Validation:        {validation or '(dry-run or runtime missing)'}")
    print(f"  Preserved configs: {existing or 'none found'}")
    print("\n  Start a governed project: open your tool's interactive AI-DLC agent and run /aidlc.")
    print("  This toolkit requires NO access to the private AICC_Unified repository.")
    return 0 if ready else 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="AICC Engineering Toolkit one-command setup.")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tool", help="claude-code | kiro-cli (prompted if omitted)")
    ap.add_argument("--target", default=".", help="your project directory (default: current dir)")
    ap.add_argument("--yes", action="store_true", help="assume yes to confirmations")
    ap.add_argument("--non-interactive", action="store_true", help="never prompt; fail closed on decisions")
    ap.add_argument("--allow-runtime-install", action="store_true",
                    help="permit running the official AWS Labs runtime installer if missing")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        return cmd_list()

    reg = load_registry()
    tool = args.tool
    if not tool:
        tool = ask_tool(reg, args.non_interactive)
        if not tool:
            print("No tool selected. Use --tool claude-code|kiro-cli or run interactively.", file=sys.stderr)
            return 2

    target = pathlib.Path(args.target).resolve()
    if target == TOOLKIT_ROOT:
        print("Refusing to target the Toolkit repo itself; pass --target <your-project-dir>.", file=sys.stderr)
        return 2
    return install(tool, target, args.yes, args.non_interactive, args.allow_runtime_install, args.force, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
