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
  5b. Write tool-neutral AI-DLC activation instructions (AGENTS.md + a thin
     CLAUDE.md pointer + a Kiro steering pointer) so BOTH tools auto-discover
     that a build request must start the governed workflow, and VERIFY the
     selected harness's engine surface was actually configured by the runtime.
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
import datetime
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import uuid
import webbrowser
import pathlib

import workbench_register as wr
import tls
import aidlc_activation
import harness_registry as hreg
from workbench_endpoint import WORKBENCH_API_ENV, resolve_api

TOOLKIT_ROOT = pathlib.Path(__file__).resolve().parent.parent
AI_DLC = TOOLKIT_ROOT / "capabilities" / "ai-dlc"
PUBLIC_REGISTRY = AI_DLC / "validators" / "public-registry.json"

# Project-local AICC config file (per the engineer's own project; portable).
AICC_CONFIG_REL = pathlib.Path(".aicc") / "config.json"
# Workbench API base resolution lives in workbench_endpoint.resolve_api():
# precedence is --workbench-api flag > $AICC_WORKBENCH_API > maintained default.
# The default host is named only in that one designated file (and README.md).

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


def _candidate_runtime_dirs() -> list[pathlib.Path]:
    """Default install locations the official AWS Labs installer uses, so we can
    rediscover `aidlc` right after a fresh install even when the PATH update is
    not yet visible to this already-running Python process (a common Windows
    gotcha: PATH changes land in the registry/new shells, not the live env)."""
    dirs: list[pathlib.Path] = []
    home = pathlib.Path.home()
    # POSIX-style default (also used under WSL).
    dirs += [home / ".aidlc" / "bin", home / ".local" / "bin"]
    # Windows default user-scope locations (non-admin installs land here).
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        dirs += [pathlib.Path(localappdata) / "aidlc" / "bin",
                 pathlib.Path(localappdata) / "Programs" / "aidlc"]
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        dirs += [pathlib.Path(userprofile) / ".aidlc" / "bin"]
    return dirs


def find_runtime_exe() -> str | None:
    """Locate the `aidlc` executable: PATH first, then the installer's known
    default directories (handles the post-install 'PATH not refreshed yet' case
    on Windows). Returns an absolute path string, or None."""
    exe = shutil.which("aidlc")
    if exe:
        return exe
    names = ["aidlc.exe", "aidlc.cmd", "aidlc.bat", "aidlc"] if os.name == "nt" else ["aidlc"]
    for d in _candidate_runtime_dirs():
        for name in names:
            cand = d / name
            if cand.exists() and cand.is_file():
                return str(cand)
    return None


def _candidate_tool_dirs() -> list[pathlib.Path]:
    """User-scope locations where AI tool CLIs commonly install, so detection
    works even when the live process PATH hasn't picked them up (the Windows
    'PATH not refreshed' gotcha). Claude Code on Windows installs to
    %USERPROFILE%\\.local\\bin\\claude.exe — exactly this case."""
    dirs: list[pathlib.Path] = []
    home = pathlib.Path.home()
    dirs += [home / ".local" / "bin", home / "bin"]
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        up = pathlib.Path(userprofile)
        dirs += [up / ".local" / "bin", up / "bin"]
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        la = pathlib.Path(localappdata)
        dirs += [la / "Programs", la / "bin"]
    # De-dup while preserving order.
    seen, out = set(), []
    for d in dirs:
        k = str(d)
        if k not in seen:
            seen.add(k); out.append(d)
    return out


def find_tool_exe(names: tuple | list) -> str | None:
    """Locate an AI tool CLI by candidate command name(s): PATH first, then the
    known user-scope install dirs (with Windows extensions). Returns an absolute
    path string, or None. Mirrors find_runtime_exe for the same Windows reason."""
    for n in names:
        hit = shutil.which(n)
        if hit:
            return hit
    exts = (".exe", ".cmd", ".bat", "") if os.name == "nt" else ("",)
    for d in _candidate_tool_dirs():
        for n in names:
            for ext in exts:
                cand = d / f"{n}{ext}"
                if cand.exists() and cand.is_file():
                    return str(cand)
    return None


def runtime_version(exe: str | None = None) -> tuple[int, int, int] | None:
    exe = exe or find_runtime_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=30)
        import re
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout)
        return tuple(int(x) for x in m.groups()) if m else None  # type: ignore
    except Exception:
        return None


def runtime_doctor_ok(exe: str | None = None) -> tuple[bool, str]:
    """Run `aidlc doctor` to validate runtime readiness. Returns (ok, summary).
    Treats a zero exit as healthy; otherwise surfaces a short diagnostic."""
    exe = exe or find_runtime_exe()
    if not exe:
        return False, "aidlc not found"
    try:
        r = subprocess.run([exe, "doctor"], capture_output=True, text=True, timeout=120)
        out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        summary = out[-1] if out else ""
        return r.returncode == 0, (summary or f"exit {r.returncode}")
    except Exception as exc:
        return False, f"could not run `aidlc doctor`: {exc}"


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


def _detected_harnesses() -> list[str]:
    """Harness ids whose CLI is installed (PATH or known user-scope dirs).
    Editors without a CLI can't be detected this way."""
    found = []
    for hid in hreg.all_ids():
        h = hreg.HARNESSES[hid]
        if h.detect_cli and find_tool_exe(h.detect_cli):
            found.append(hid)
    return found


def ask_tool(reg: dict, non_interactive: bool) -> str | None:
    """Select a harness. Reuses an already-installed tool when exactly one is
    detected; otherwise offers all seven supported harnesses."""
    detected = _detected_harnesses()
    if len(detected) == 1:
        print(f"Detected installed tool: {detected[0]} ({hreg.HARNESSES[detected[0]].display_name}) — reusing it.")
        return detected[0]
    if non_interactive:
        return None
    cert = certified(reg)
    opts = hreg.all_ids()
    print("Which AI coding tool do you use? (all are official AWS Labs AI-DLC harnesses)")
    for i, hid in enumerate(opts, 1):
        h = hreg.HARNESSES[hid]
        legacy = {"claude": "claude-code", "kiro": "kiro-cli"}.get(hid, hid)
        tag = " [AICC-certified]" if legacy in cert else ""
        seen = " (detected)" if hid in detected else ""
        print(f"  {i}. {hid:<10} {h.display_name}{tag}{seen}")
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


# Toolkit-integration status per harness — HONEST, and deliberately conservative.
# This is NOT the AICC certification state (that lives in the public registry);
# it is "how far the Toolkit's own integration for this harness is proven":
#   VERIFIED  — exercised end-to-end against the real tool on a real machine.
#   PARTIAL   — logic + automated/mocked tests here, plus prior real runs on the
#               tool, but current Windows end-to-end acceptance still pending.
#   UNTESTED  — registry + config/verify logic in place; NO real-machine run yet.
# Nothing here is marked VERIFIED until a real-machine acceptance is recorded.
HARNESS_INTEGRATION_STATUS = {
    "claude": "PARTIAL",
    "kiro": "PARTIAL",
    "kiro-ide": "UNTESTED",
    "codex": "UNTESTED",
    "cursor": "UNTESTED",
    "opencode": "UNTESTED",
    "copilot": "UNTESTED",
}


def cmd_list_harnesses() -> int:
    """Show ALL seven official AI-DLC harnesses the Toolkit can configure, with
    honest Toolkit-integration status and invocation. Separate from `--list`,
    which reports AICC CERTIFICATION (certified install options only)."""
    reg = load_registry()
    cert = certified(reg)
    print("AICC Engineering Toolkit — official AWS Labs AI-DLC harnesses (configurable)")
    print("Runtime prerequisite (one-time, per machine): AWS Labs aidlc; `aidlc config --harness <id>` selects a project surface.\n")
    print(f"  {'harness':<10} {'tool':<16} {'invoke':<7} {'AICC cert':<11} {'toolkit':<9} onboarding surface")
    print(f"  {'-'*10} {'-'*16} {'-'*7} {'-'*11} {'-'*9} {'-'*34}")
    for hid in hreg.all_ids():
        h = hreg.HARNESSES[hid]
        legacy = {"claude": "claude-code", "kiro": "kiro-cli"}.get(hid, hid)
        cstate = next((t["certification_state"] for t in reg["tools"] if t["id"] == legacy), "UNCERTIFIED")
        status = HARNESS_INTEGRATION_STATUS.get(hid, "UNTESTED")
        print(f"  {hid:<10} {h.display_name:<16} {h.invoke:<7} {cstate:<11} {status:<9} {h.onboarding_file}")
    print("\nAICC cert = AICC certification (from the public registry projection).")
    print("toolkit   = how far the Toolkit's own integration is PROVEN (VERIFIED/PARTIAL/UNTESTED).")
    print("Only claude & kiro are AICC-CERTIFIED; the others are upstream-supported and")
    print("require real-machine acceptance before any VERIFIED/certified claim.")
    print("Coexistence: kiro, kiro-ide, codex, cursor, opencode share the root AGENTS.md block;")
    print("GitHub Copilot's root block is exclusive (configure it alone).")
    return 0


def _runtime_guidance(plat: dict) -> str:
    if plat["is_windows"]:
        return (f"On Windows PowerShell, install the runtime with:\n"
                f"    irm {INSTALL_PS1} | iex\n"
                f"(POSIX install.sh does NOT run in PowerShell. WSL2 users use the macOS/Linux command.)")
    return f"Install the official runtime with:\n    curl -fsSL {INSTALL_SH} | sh"


def _run_official_installer(plat: dict) -> tuple[int, str]:
    """Invoke the OFFICIAL AWS Labs installer for this OS. Never reimplements it;
    integrity (checksums + SLSA provenance) is enforced by that installer. On
    Windows uses PowerShell (`irm … install.ps1 | iex`) in user scope so a
    standard non-admin install works where permitted. Returns (returncode, how)."""
    if plat["is_windows"]:
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            return 127, "PowerShell not found on PATH"
        # -NoProfile for a clean env; the official one-liner fetches + runs the
        # signed installer. Passed as an argument list (no shell string), so a
        # project path with spaces elsewhere is irrelevant here.
        cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               f"irm {INSTALL_PS1} | iex"]
        r = subprocess.run(cmd, timeout=900)
        return r.returncode, "powershell"
    # POSIX: the official shell installer. shell=True is required for the pipe;
    # the command is a fixed, trusted literal (no user input interpolated).
    r = subprocess.run(f"curl -fsSL {INSTALL_SH} | sh", shell=True, timeout=900)
    return r.returncode, "sh"


def ensure_runtime(plat: dict, assume_yes: bool, non_interactive: bool, allow_install: bool,
                   dry_run: bool) -> tuple[bool, str, str | None]:
    """Ensure the OFFICIAL aidlc runtime is present and compatible.

    Returns (runtime_ready, message, exe_path). Installs the OFFICIAL runtime
    only with explicit consent; never bundles or rewrites it. After an install
    it rediscovers the executable even if the PATH update is not yet visible to
    this process, then validates readiness with `aidlc doctor`.
    """
    exe = find_runtime_exe()
    ver = runtime_version(exe)
    if ver and ver >= MIN_RUNTIME:
        return True, f"existing compatible runtime {'.'.join(map(str, ver))} preserved", exe
    if ver and ver < MIN_RUNTIME:
        return (False,
                f"runtime {'.'.join(map(str, ver))} is below the required {'.'.join(map(str, MIN_RUNTIME))}; "
                f"update it: `aidlc update` (from {RUNTIME_REPO})",
                exe)

    # No runtime present.
    if not plat["supported"]:
        return (False,
                f"the official AI-DLC runtime has no asset for {plat['os']}/{plat['arch']}; "
                f"see {RUNTIME_REPO} releases for supported platforms",
                None)

    guidance = _runtime_guidance(plat)

    if dry_run:
        return (False,
                f"DRY-RUN: runtime not found; would (with your consent) run the official "
                f"{RUNTIME_REPO} installer. Nothing downloaded or installed.\n    {guidance}",
                None)

    if not allow_install:
        return (False,
                "AI-DLC runtime not found. This toolkit does not bundle it (third-party, MIT-0).\n"
                + guidance + "\nThen re-run this installer. Or pass --allow-runtime-install to run the "
                "official installer now (requires explicit confirmation).",
                None)

    # Explicit consent before executing ANY remote install script.
    src = INSTALL_PS1 if plat["is_windows"] else INSTALL_SH
    if not confirm(f"Install the official AWS Labs AI-DLC runtime (MIT-0) from {src}?",
                   assume_yes, non_interactive):
        return (False, "runtime install declined; " + guidance, None)

    try:
        rc, how = _run_official_installer(plat)
    except Exception as exc:
        return (False, f"runtime install failed: {exc}; " + guidance, None)
    if rc != 0:
        return (False,
                f"official installer ({how}) exited {rc}; see output above. " + guidance,
                None)

    # Rediscover the freshly installed exe (PATH may not be refreshed in THIS
    # process yet — especially on Windows). Look in the known install dirs.
    exe2 = find_runtime_exe()
    v2 = runtime_version(exe2)
    if not (v2 and v2 >= MIN_RUNTIME):
        return (False,
                "installer ran but a compatible `aidlc` was not detected yet. Open a NEW terminal "
                "(so PATH refreshes) and re-run this installer — your project identity is reused.",
                exe2)

    # Validate readiness with the runtime's own doctor.
    ok, summary = runtime_doctor_ok(exe2)
    msg = f"installed official runtime {'.'.join(map(str, v2))}"
    if ok:
        msg += "; `aidlc doctor` OK"
    else:
        msg += f"; `aidlc doctor` reported: {summary}"
    return (ok, msg, exe2)


def preserve_check(target: pathlib.Path, harness: str) -> list[str]:
    """Report existing tool configs that must be preserved (never silently
    overwritten) — across ALL supported harnesses, so switching tools never
    clobbers another harness's configuration."""
    present = []
    rels = ["CLAUDE.md", ".claude", ".claude/agents", ".claude/skills", ".claude/hooks",
            ".kiro", ".kiro/hooks", ".kiro/steering", ".codex", ".cursor", ".opencode",
            ".github", "AGENTS.md", "aidlc", ".aidlc"]
    for rel in rels:
        if (target / rel).exists():
            present.append(rel)
    return present


def _safe_copy_file(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy one file, clearing a read-only destination first (Windows/OneDrive)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            dst.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
    shutil.copy2(src, dst)


def _safe_sync_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy `src` into `dst` file-by-file WITHOUT deleting `dst` first.

    This replaces the old `rmtree(dst); copytree(src, dst)` pattern, which was
    both unsafe (destroys the destination before the copy succeeds) and fragile
    on Windows/OneDrive, where an open handle, a lazy-sync placeholder, or a
    read-only attribute makes a recursive delete fail with WinError 5. Copying
    in place:
      - never recursively deletes a directory (so engineer files under the tree
        are never destroyed),
      - is idempotent and resumable: a re-run or an interrupted run just
        re-copies files; partial state is simply overwritten on the next pass,
      - clears a destination file's read-only bit (common on OneDrive) before
        overwriting it, instead of failing.
    Files that exist only in `dst` are left untouched (non-destructive); the
    AICC-managed trees here are fully specified by `src`, so this converges to
    the shipped content without removing anything the engineer added alongside.
    """
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = pathlib.Path(root).relative_to(src)
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            s = pathlib.Path(root) / f
            d = out_dir / f
            # On Windows/OneDrive a destination file may be read-only; clear it
            # so the overwrite succeeds instead of raising PermissionError.
            if d.exists():
                try:
                    d.chmod(stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
            shutil.copy2(s, d)


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
        # Non-destructive in-place sync (no rmtree): safe on Windows/OneDrive and
        # resumable after an interrupted run.
        try:
            _safe_sync_tree(src, dst)
            done.append(f"{name}: installed")
        except OSError as exc:
            done.append(f"{name}: SKIPPED ({exc.__class__.__name__}: {exc}); existing files preserved")

    # Phase 3: ship the automatic Workbench sync client + hook definitions into
    # the engineer's project so lifecycle progress syncs with no manual step.
    inst_dst = dest / "installer"
    if not dry_run:
        inst_dst.mkdir(parents=True, exist_ok=True)
        for fname in ("workbench_sync.py", "workbench_register.py"):
            src_f = TOOLKIT_ROOT / "installer" / fname
            if src_f.exists():
                _safe_copy_file(src_f, inst_dst / fname)
        hooks_src = TOOLKIT_ROOT / "installer" / "hooks"
        if hooks_src.exists():
            # Non-destructive: sync hook files in place; NEVER rmtree the dir.
            # This is the exact operation that crashed on OneDrive (WinError 5).
            try:
                _safe_sync_tree(hooks_src, inst_dst / "hooks")
                done.append("workbench sync client + hooks: installed under .aicc/ai-dlc/installer/")
            except OSError as exc:
                done.append(f"workbench sync hooks: SKIPPED ({exc.__class__.__name__}: {exc}); "
                            "existing hook files preserved")
    else:
        done.append("workbench sync client + hooks: DRY-RUN would install")
    return done


def wire_sync_hook(target: pathlib.Path, harness: str, dry_run: bool) -> str:
    """Wire the automatic Workbench-sync hook into the engineer's harness config
    WITHOUT overwriting their existing agents/skills/hooks/settings.

    Kiro  : drop aicc-workbench-sync.kiro.hook into .kiro/hooks/ (adds one file;
            never touches other hooks).
    Claude: merge a single Stop hook into .claude/settings.json's hooks map
            (preserving every existing hook and setting).
    Idempotent: re-running does not duplicate the entry. Returns a status line.
    """
    hooks_dir = target / ".aicc" / "ai-dlc" / "installer" / "hooks"
    if dry_run:
        return "sync hook: DRY-RUN would wire into the harness config"

    if harness == "kiro":
        src = hooks_dir / "aicc-workbench-sync.kiro.hook"
        if not src.exists():
            return "sync hook: source hook missing (skipped)"
        dst_dir = target / ".kiro" / "hooks"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / "aicc-workbench-sync.kiro.hook"
        try:
            _safe_copy_file(src, dst)   # adds/refreshes only this one hook file (read-only safe)
        except OSError as exc:
            return f"sync hook: could not write {dst.name} ({exc.__class__.__name__}); other Kiro hooks preserved"
        return f"sync hook: installed {dst.relative_to(target)} (other Kiro hooks preserved)"

    if harness == "claude":
        src = hooks_dir / "aicc-workbench-sync.claude.json"
        if not src.exists():
            return "sync hook: source hook missing (skipped)"
        try:
            snippet = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "sync hook: could not read Claude hook snippet (skipped)"
        stop_entries = (snippet.get("hooks") or {}).get("Stop") or []
        settings_path = target / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return "sync hook: existing .claude/settings.json is unreadable; left untouched (wire the Stop hook manually)"
        hooks = settings.setdefault("hooks", {})
        stop = hooks.setdefault("Stop", [])
        marker = "installer/workbench_sync.py"
        already = any(marker in json.dumps(e) for e in stop)
        if not already:
            stop.extend(stop_entries)
            settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
            return "sync hook: merged Stop hook into .claude/settings.json (existing hooks preserved)"
        return "sync hook: already present in .claude/settings.json (no change)"

    return "sync hook: no wiring for this harness"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_project_config(target: pathlib.Path) -> dict:
    """Read the project-local AICC config, or {} if absent/unreadable."""
    cfg_path = target / AICC_CONFIG_REL
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def ensure_project_identity(target: pathlib.Path, tool: str, harness: str, dry_run: bool) -> dict:
    """Generate (or reuse) a stable local project identity and persist it.

    - Reuses an existing local_project_id on repeated installations.
    - Merges into any existing config.json; never clobbers it.
    - Writes nothing in dry-run.
    Returns the (in-memory) config dict reflecting the identity.
    """
    cfg = load_project_config(target)

    # Stable local id: generate once, reuse forever.
    if not cfg.get("local_project_id"):
        cfg["local_project_id"] = uuid.uuid4().hex
        cfg.setdefault("created_at", _now_iso())
    cfg["tool"] = tool
    cfg["harness"] = harness
    cfg["updated_at"] = _now_iso()
    cfg.setdefault("schema_version", "1.0.0")
    # Workbench connection scaffold (filled by registration).
    wb = cfg.get("workbench")
    if not isinstance(wb, dict):
        wb = {}
    wb.setdefault("status", wr.STATUS_NOT_CONNECTED)
    cfg["workbench"] = wb

    if not dry_run:
        save_project_config(target, cfg)
    return cfg


def save_project_config(target: pathlib.Path, cfg: dict) -> None:
    cfg_path = target / AICC_CONFIG_REL
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def register_with_workbench(target: pathlib.Path, cfg: dict, tool: str, harness: str,
                            api: str, api_source: str, dry_run: bool) -> tuple[str, str]:
    """Attempt project registration against the Workbench contract.

    Returns (status, message). NEVER fabricates success: an unreachable backend
    yields NOT_CONNECTED; a reachable-but-bad server yields FAILED. On genuine
    success the server-issued project_id / workbench_url / pending stages are
    persisted into cfg['workbench']. Registration is idempotent, so a retry
    after a network failure reuses the same local_project_id and never creates a
    duplicate project.
    """
    if not api:
        # Only reachable if the maintained default is empty AND no override is
        # set — honest, no fabrication.
        cfg["workbench"]["status"] = wr.STATUS_NOT_CONNECTED
        if not dry_run:
            save_project_config(target, cfg)
        return (wr.STATUS_NOT_CONNECTED,
                "no Workbench API resolved (pass --workbench-api or set $%s)." % WORKBENCH_API_ENV)
    if dry_run:
        return (wr.STATUS_NOT_CONNECTED,
                f"DRY-RUN: would POST registration to {api}{wr.REGISTER_PATH} "
                f"(endpoint source: {api_source}); no project created, nothing written.")

    try:
        result = wr.register_project(api, cfg["local_project_id"], tool, harness)
    except wr.RegisterError as exc:
        cfg["workbench"] = {
            "status": exc.status,
            "api": api,
            "last_error": str(exc),
            "checked_at": _now_iso(),
        }
        # Keep the stable local_project_id so a retry re-registers the SAME
        # project (idempotent) rather than creating a duplicate.
        save_project_config(target, cfg)
        return (exc.status, str(exc))

    cfg["workbench"] = {
        "status": wr.STATUS_REGISTERED,
        "api": api,
        "project_id": result["project_id"],
        "workbench_url": result["workbench_url"],
        "stages": result["stages"],
        "registered_at": _now_iso(),
    }
    # Phase 3: persist the UPDATE capability (if the backend returned one) so the
    # sync hook can push validated lifecycle updates automatically. This is a
    # local secret — stored only in the engineer's own .aicc/config.json, never
    # printed, never placed in the view URL, never committed by the toolkit.
    if result.get("update_token"):
        cfg["workbench"]["update_token"] = result["update_token"]
    save_project_config(target, cfg)
    return (wr.STATUS_REGISTERED, f"registered as project {result['project_id']}")


def maybe_open_browser(url: str, open_browser: bool) -> str:
    """Open the engineer's OWN project URL in the default browser when allowed.

    Only ever called with a server-returned per-project URL from a SUCCESSFUL
    registration — never the certified showcase. Guarded for headless envs.
    """
    if not open_browser:
        return "browser open suppressed (--no-browser / non-interactive / dry-run)"
    if not url:
        return "no project URL to open"
    try:
        if webbrowser.open(url):
            return f"opened {url} in your default browser"
        return f"could not open a browser automatically; open your project manually: {url}"
    except Exception as exc:
        return f"could not open a browser ({exc}); open your project manually: {url}"


def install(tool: str, target: pathlib.Path, assume_yes: bool, non_interactive: bool,
            allow_runtime_install: bool, force: bool, dry_run: bool,
            workbench_api: str, api_source: str, open_browser: bool,
            relax_tls_keyusage: bool = False) -> int:
    reg = load_registry()
    cert = certified(reg)
    plat = detect_platform()

    print(f"== AICC Engineering Toolkit setup ==")
    print(f"OS/arch: {plat['os']}/{plat['arch']}  supported={plat['supported']}{' (WSL)' if plat['in_wsl'] else ''}")
    if not plat["supported"]:
        print(f"BLOCKED: platform {plat['os']}/{plat['arch']} is not in the official runtime asset matrix.", file=sys.stderr)
        return 2

    # Resolve to an official harness via the central registry (accepts a harness
    # id OR a legacy tool id like 'claude-code'/'kiro-cli').
    hinfo = hreg.resolve(tool)
    if not hinfo:
        print(f"BLOCKED: '{tool}' is not an official AI-DLC harness. Supported: "
              f"{', '.join(hreg.all_ids())}.", file=sys.stderr)
        return 2
    harness = hinfo.id

    # Honest certification labeling. kiro/claude are AICC-CERTIFIED; the other
    # five are officially UPSTREAM-supported but NOT AICC-certified — the Toolkit
    # can configure them, but we never claim certification. Legacy tool ids map
    # back to the public-registry rows.
    legacy_tool = {"claude": "claude-code", "kiro": "kiro-cli"}.get(harness, harness)
    cert_state = next((t["certification_state"] for t in reg["tools"] if t["id"] == legacy_tool), "UNCERTIFIED")
    is_certified = legacy_tool in cert
    if not is_certified:
        print(f"NOTE: '{harness}' ({hinfo.display_name}) is an official AWS Labs AI-DLC harness "
              f"SUPPORTED by this Toolkit, but it is {cert_state} for AICC certification — "
              f"its Toolkit integration still requires real-machine acceptance. Configuring anyway "
              f"(honestly, with verification); this is NOT an AICC certification.")
        if not confirm(f"Proceed configuring the uncertified '{harness}' harness?", assume_yes, non_interactive):
            print(f"BLOCKED: declined configuring uncertified harness '{harness}'.", file=sys.stderr)
            return 2

    # Codex requires the target to be a git repository (upstream prerequisite).
    if hinfo.requires_git_repo and not dry_run:
        if not (target / ".git").exists():
            print(f"NOTE: {hinfo.display_name} requires the project to be a git repository "
                  f"(for project hook discovery). Run `git init` in {target} before using AI-DLC.")

    # Tool CLI presence (editors like Kiro IDE / Cursor can't be PATH-detected).
    if hinfo.is_editor and not hinfo.detect_cli:
        tool_present = False
        print(f"Tool `{hinfo.display_name}`: editor (cannot auto-detect from PATH; "
              f"ensure it is installed to run the lifecycle)")
    else:
        # PATH-aware + user-scope detection (finds e.g. %USERPROFILE%\.local\bin\claude.exe
        # even when it is not on the live process PATH).
        found_exe = find_tool_exe(hinfo.detect_cli)
        tool_present = found_exe is not None
        print(f"Tool `{hinfo.display_name}` ({'/'.join(hinfo.detect_cli) or 'editor'}): "
              f"{'found: ' + found_exe if tool_present else 'NOT found (install it from its vendor to run the lifecycle)'}")

    # Runtime
    rt_ready, rt_msg, rt_exe = ensure_runtime(plat, assume_yes, non_interactive,
                                              allow_runtime_install, dry_run)
    print(f"Runtime: {rt_msg}")

    # Preservation (never silently overwrite)
    target.mkdir(parents=True, exist_ok=True)
    existing = preserve_check(target, harness)
    if existing:
        print(f"Existing configs detected (will be PRESERVED, not overwritten): {existing}")

    # Apply AICC standard (namespaced, non-destructive)
    print("Applying AICC AI-DLC standard (under <project>/.aicc/ai-dlc/, non-destructive):")
    for line in apply_aicc_standard(target, tool, force, dry_run):
        print(f"   {line}")

    # `harness` was resolved from the registry above.

    # AI-DLC activation instructions: tool-neutral AGENTS.md + a thin CLAUDE.md
    # pointer + a Kiro steering pointer, so BOTH tools auto-discover that a build
    # request must start the governed AI-DLC workflow. Non-destructive; it never
    # copies the methodology. Written independently of the runtime and of
    # Workbench, so a build request activates AI-DLC even if those are absent.
    print("Writing AI-DLC activation instructions (AGENTS.md / CLAUDE.md / Kiro steering):")
    for line in aidlc_activation.write_activation_instructions(target, harness, dry_run):
        print(f"   {line}")

    # Harness engine config via the OFFICIAL runtime (only if runtime ready and
    # not dry-run). Version-aware + VERIFIED: we confirm the engine surface
    # (.claude/ or .kiro/) actually exists before reporting it wired. This runs
    # BEFORE any Workbench step, so registration/TLS problems can never block it.
    harness_wired = False
    harness_msg = "skipped"
    # Use the resolved runtime exe (handles PATH-not-refreshed), falling back to
    # a bare "aidlc" on PATH.
    aidlc_exe = rt_exe or find_runtime_exe() or "aidlc"
    if dry_run:
        harness_msg = aidlc_activation.configure_harness(aidlc_exe, target, harness, dry_run=True)[1]
        print(f"   {harness_msg}")
    elif rt_ready:
        if confirm(f"Configure the official AI-DLC '{harness}' harness in {target}? "
                   "(preserves existing files; verifies the engine surface)",
                   assume_yes, non_interactive):
            harness_wired, harness_msg = aidlc_activation.configure_harness(
                aidlc_exe, target, harness, dry_run=False)
            print(f"   {harness_msg}")
        else:
            harness_msg = "declined; run `aidlc config` yourself and choose the %s harness" % harness
            print(f"   harness config {harness_msg}")
    else:
        harness_msg = "runtime not ready; configure the harness after the runtime is installed"
        print(f"   {harness_msg}")

    # Phase 3: wire the automatic Workbench-sync hook (non-destructive).
    print(f"   {wire_sync_hook(target, harness, dry_run)}")

    # Post-install validation
    val = target / ".aicc" / "ai-dlc" / "validators"
    validation = {}
    if not dry_run and (val / "exporter" / "test_evidence.py").exists():
        rv = subprocess.run([sys.executable, str(val / "exporter" / "test_evidence.py")],
                           capture_output=True, text=True, cwd=str(val / "exporter"))
        validation["evidence_contract"] = "PASS" if rv.returncode == 0 else "FAIL"

    # Project identity (stable local id, reused on re-install) + config.json
    reused = bool(load_project_config(target).get("local_project_id"))
    cfg = ensure_project_identity(target, tool, harness, dry_run)
    print(f"\nProject identity: local_project_id={cfg['local_project_id']} "
          f"({'reused from existing config' if reused else 'newly generated'})"
          f"{' (dry-run: not written)' if dry_run else ''}")

    # Workbench registration (honest; never fabricated). The endpoint is the
    # maintained default unless overridden by --workbench-api / env.
    print(f"Workbench endpoint: {workbench_api or '(none)'} (source: {api_source})")
    # Apply the TLS policy (full verification always; opt-in Key Usage relax).
    wr.set_tls_policy(relax_tls_keyusage)
    if relax_tls_keyusage:
        print("Workbench TLS: strict X.509 Key Usage check RELAXED by request "
              "(chain + hostname verification remain enforced).")
    wb_status, wb_msg = register_with_workbench(target, cfg, tool, harness,
                                                workbench_api, api_source, dry_run)
    print(f"Workbench registration: {wb_status} — {wb_msg}")

    # Automatic Workbench opening — ONLY on a genuine registration success, and
    # ONLY the server-returned per-project URL (never our certified showcase).
    browser_msg = None
    if wb_status == wr.STATUS_REGISTERED:
        url = cfg.get("workbench", {}).get("workbench_url", "")
        browser_msg = maybe_open_browser(url, open_browser and not dry_run)
        print(f"Workbench: {browser_msg}")
        print("Your six lifecycle stages (Requirements, Design, Approval, Code, Tests, Evidence) "
              "start as PENDING and update as you submit evidence.")
        print(f"Next: open {tool.replace('-', ' ')} ("
              f"{'claude' if harness == 'claude' else 'kiro-cli chat'}) and describe the application you want to build.")

    # Report. In dry-run we NEVER claim a successful install — we only describe
    # what would happen.
    ready = rt_ready and tool_present
    if dry_run:
        result_label = "DRY-RUN (no changes made; nothing installed, written, registered, or opened)"
    else:
        result_label = "READY" if ready else "BLOCKED (see above)"
    print("\n== Setup report ==")
    print(f"  Result:            {result_label}")
    print(f"  Tool:              {hinfo.display_name} ({harness}) — AICC {cert_state}"
          f"{' (' + cert[legacy_tool]['qualification'] + ')' if is_certified and cert.get(legacy_tool, {}).get('qualification') else ''}")
    print(f"  Invoke in-tool:    {hinfo.invoke}  (not all harnesses use /aidlc; Codex uses $aidlc)")
    print(f"  Platform:          {plat['os']}/{plat['arch']}")
    print(f"  Runtime:           {'ready' if rt_ready else 'NOT ready — ' + rt_msg.splitlines()[0]}")
    print(f"  AI-DLC harness:    {harness} — {'CONFIGURED (engine surface verified)' if harness_wired else 'NOT confirmed'}")
    if not harness_wired and not dry_run:
        print(f"                     {harness_msg}")
    print(f"  AI-DLC activation: AGENTS.md + CLAUDE.md + Kiro steering written — a 'build ...' request")
    print(f"                     starts the governed workflow (requirements + human approval) in either tool")
    print(f"  AICC standard:     installed under {target}/.aicc/ai-dlc/")
    print(f"  Approval control:  genuine human Plan Approval is enforced by the runtime's prompt-submit hook")
    print(f"                     (verify: `aidlc doctor`, and `preflight.py --tool {tool} --require-human-turn`)")
    print(f"  Validation:        {validation or '(dry-run or runtime missing)'}")
    print(f"  Preserved configs: {existing or 'none found'}")
    print(f"  Project id:        {cfg['local_project_id']} (stable, reused on re-install)")
    print(f"  Project config:    {target / AICC_CONFIG_REL}")
    if wb_status == wr.STATUS_REGISTERED:
        print(f"  Workbench:         READY — {cfg['workbench']['workbench_url']}")
    elif dry_run:
        print(f"  Workbench:         (dry-run) would register at {workbench_api} (source: {api_source})")
    else:
        print(f"  Workbench:         {wb_status} ({wb_msg.splitlines()[0]})")
        print(f"                     Local setup is unaffected. Re-run the installer to retry;")
        print(f"                     your stable project id is reused, so no duplicate project is created.")
    print("\n  Start a governed project: open your tool's interactive AI-DLC agent and run /aidlc.")
    print("  This toolkit requires NO access to the private AICC_Unified repository.")
    return 0 if ready else 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="AICC Engineering Toolkit one-command setup.")
    ap.add_argument("--list", action="store_true", help="list AICC-certified install options")
    ap.add_argument("--list-harnesses", action="store_true",
                    help="list ALL seven official AI-DLC harnesses the Toolkit can configure, with honest status")
    ap.add_argument("--tool", help="legacy alias for --harness (claude-code | kiro-cli)")
    ap.add_argument("--harness", help="official harness id: " + " | ".join(hreg.all_ids()) + " (prompted if omitted)")
    ap.add_argument("--target", default=".", help="your project directory (default: current dir)")
    ap.add_argument("--yes", action="store_true", help="assume yes to confirmations")
    ap.add_argument("--non-interactive", action="store_true", help="never prompt; fail closed on decisions")
    ap.add_argument("--allow-runtime-install", action="store_true",
                    help="permit running the official AWS Labs runtime installer if missing")
    ap.add_argument("--workbench-api", default=None,
                    help=f"override the Workbench API base URL for project registration "
                         f"(else ${WORKBENCH_API_ENV}, else the maintained default endpoint).")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not open the Workbench URL in a browser (headless / automation)")
    ap.add_argument("--allow-legacy-tls-keyusage", action="store_true", default=None,
                    help="opt-in: behind a corporate SSL-inspection proxy whose root CA lacks the "
                         "X.509 Key Usage extension, relax ONLY that strict check (chain + hostname "
                         f"verification stay enforced). Off by default; env ${tls.RELAX_KEYUSAGE_ENV}=1 "
                         "also enables it. Prefer having IT re-issue the CA.")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        return cmd_list()
    if args.list_harnesses:
        return cmd_list_harnesses()

    reg = load_registry()
    tool = args.harness or args.tool
    if not tool:
        tool = ask_tool(reg, args.non_interactive)
        if not tool:
            print("No harness selected. Use --harness <id> (see --list-harnesses) or run interactively.",
                  file=sys.stderr)
            return 2

    target = pathlib.Path(args.target).resolve()
    if target == TOOLKIT_ROOT:
        print("Refusing to target the Toolkit repo itself; pass --target <your-project-dir>.", file=sys.stderr)
        return 2
    # Resolve the Workbench endpoint: flag > env > maintained default.
    workbench_api, api_source = resolve_api(args.workbench_api)
    # Browser opening is suppressed for headless/automation modes.
    open_browser = not (args.no_browser or args.non_interactive or args.dry_run)
    # TLS policy: resolve the opt-in Key Usage relaxation (flag > env > off).
    relax_tls = tls.relax_requested(args.allow_legacy_tls_keyusage)
    return install(tool, target, args.yes, args.non_interactive, args.allow_runtime_install,
                   args.force, args.dry_run, workbench_api, api_source, open_browser,
                   relax_tls_keyusage=relax_tls)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
