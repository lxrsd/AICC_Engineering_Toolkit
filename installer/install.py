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
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
import webbrowser
import pathlib

import workbench_register as wr
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

    # Phase 3: ship the automatic Workbench sync client + hook definitions into
    # the engineer's project so lifecycle progress syncs with no manual step.
    inst_dst = dest / "installer"
    if not dry_run:
        inst_dst.mkdir(parents=True, exist_ok=True)
        for fname in ("workbench_sync.py", "workbench_register.py"):
            src_f = TOOLKIT_ROOT / "installer" / fname
            if src_f.exists():
                shutil.copy2(src_f, inst_dst / fname)
        hooks_src = TOOLKIT_ROOT / "installer" / "hooks"
        if hooks_src.exists():
            hooks_dst = inst_dst / "hooks"
            if hooks_dst.exists():
                shutil.rmtree(hooks_dst)
            shutil.copytree(hooks_src, hooks_dst)
        done.append("workbench sync client + hooks: installed under .aicc/ai-dlc/installer/")
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
        shutil.copy2(src, dst)   # adds/refreshes only this one hook file
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
            workbench_api: str, api_source: str, open_browser: bool) -> int:
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
    rt_ready, rt_msg, rt_exe = ensure_runtime(plat, assume_yes, non_interactive,
                                              allow_runtime_install, dry_run)
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
    # Use the resolved runtime exe (handles the case where PATH is not refreshed
    # in this process yet), falling back to a bare "aidlc" on PATH.
    aidlc_exe = rt_exe or find_runtime_exe() or "aidlc"
    if rt_ready and not dry_run:
        if confirm(f"Run `aidlc config --harness {harness}` in {target}? (preserves existing files; shows a plan)",
                   assume_yes, non_interactive):
            try:
                r = subprocess.run([aidlc_exe, "config", "--harness", harness, "--yes"],
                                   cwd=str(target), capture_output=True, text=True, timeout=180)
                print((r.stdout or "")[:1000])
                harness_wired = r.returncode == 0
                if r.returncode != 0:
                    print(f"   aidlc config exited {r.returncode}: {(r.stderr or '')[:300]}", file=sys.stderr)
            except Exception as exc:
                print(f"   could not run aidlc config: {exc}", file=sys.stderr)
        else:
            print("   harness config skipped (run `aidlc config --harness %s` yourself when ready)" % harness)

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
    print(f"  Tool:              {tool} (CERTIFIED{' — ' + cert[tool]['qualification'] if cert[tool].get('qualification') else ''})")
    print(f"  Platform:          {plat['os']}/{plat['arch']}")
    print(f"  Runtime:           {'ready' if rt_ready else 'NOT ready — ' + rt_msg.splitlines()[0]}")
    print(f"  Harness wired:     {'yes' if harness_wired else 'no (needs runtime + aidlc config)'}")
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
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tool", help="claude-code | kiro-cli (prompted if omitted)")
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
    # Resolve the Workbench endpoint: flag > env > maintained default.
    workbench_api, api_source = resolve_api(args.workbench_api)
    # Browser opening is suppressed for headless/automation modes.
    open_browser = not (args.no_browser or args.non_interactive or args.dry_run)
    return install(tool, target, args.yes, args.non_interactive, args.allow_runtime_install,
                   args.force, args.dry_run, workbench_api, api_source, open_browser)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
