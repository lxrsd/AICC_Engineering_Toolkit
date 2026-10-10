#!/usr/bin/env python3
"""AICC AI-DLC preflight diagnostics.

Fails clearly when the AI-DLC agent, the mandatory approval hooks, the
framework version, or the approval machinery are missing, disabled, or not
executing, and when a tree that should be a fresh clone still carries another
engineer's protected runtime state.

Configuration presence is never treated as compliance on its own: the
`--mode session` and `--require-human-turn` checks require evidence that the
hooks actually executed in the ACTIVE workflow.

Stdlib-only and portable: it reads only the local clone, the process
environment, and PATH; it hardcodes no personal path, token, username, or
account identifier, and it never reads protected session receipts.

Usage:
    preflight.py --tool <kiro-cli|kiro-ide|claude-code> [--repo-root <dir>]
                 [--mode setup|session] [--require-human-turn] [--json]

Modes:
    setup    (default) Fresh-clone checks, run from a terminal BEFORE the first
             governed prompt: runtime version, harness files, mandatory hooks
             wired and not disabled, no inherited protected state.
    session  Run from INSIDE the agent session (e.g. its shell tool) after the
             first prompt: detects the execution surface and requires proof
             that the human-turn hook executed for the active workflow.

--require-human-turn
    Use before governed Construction / for certification: the active
    workflow's ledger must hold a genuine HUMAN_TURN, and every
    approval-sensitive event must be backed by one: PLAN_APPROVAL_RECORDED by a
    same-session turn after its prompt; GATE_APPROVED, GATE_REJECTED (Request
    Changes) and AUTONOMY_MODE_SET autonomous by a turn since the previous gate
    resolution. HUMAN_TURN events recorded for sub-agent hand-backs (Origin
    field, or within 2 s after SUBAGENT_COMPLETED on older ledgers) never count
    as backing. Events from any other workflow are ignored.

Exit 0 if all REQUIRED checks pass, 1 if any required check fails, 2 on usage
error. Checks tied to a known-blocked environment are reported honestly as
FAIL rather than skipped.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

SUPPORTED_TOOLS = {
    "kiro-cli": {"engine_dir": ".kiro", "agent_file": ".kiro/agents/aidlc.json",
                 "hook_file": ".kiro/hooks/aidlc-record-human-turn.kiro.hook"},
    "kiro-ide": {"engine_dir": ".kiro", "agent_file": ".kiro/agents/aidlc.json",
                 "hook_file": ".kiro/hooks/aidlc-record-human-turn.kiro.hook"},
    "claude-code": {"engine_dir": ".claude", "agent_file": ".claude/CLAUDE.md",
                    "hook_file": None},
}

# Claude Code hooks that the AI-DLC approval controls depend on.
# (event, matcher-substring or None, hook command)
CLAUDE_MANDATORY_HOOKS = [
    ("UserPromptSubmit", None, "aidlc engine hook record-human-turn"),
    ("PostToolUse", "AskUserQuestion", "aidlc engine hook record-human-turn"),
    ("PreToolUse", "Write", "aidlc engine hook plan-approval-guard"),
    ("PreToolUse", "Bash", "aidlc engine hook state-transition-guard"),
    ("PreToolUse", "Write", "aidlc engine hook review-freeze"),
    ("SessionStart", None, "aidlc engine hook session-start"),
]

# Claude execution surfaces, keyed by the CLAUDE_CODE_ENTRYPOINT value the
# Claude Code runtime exports to the shell it runs tools in.
#   VERIFIED     - a real AICC governed run recorded genuine HUMAN_TURN +
#                  PLAN_APPROVAL_RECORDED on this surface.
#   UNVERIFIED   - runs Claude Code with project hooks, but no AICC governed
#                  run has been verified on it yet. Allowed, reported as such.
#   UNSUPPORTED  - cannot run the governed lifecycle (no interactive human
#                  turn, or no project hooks).
CLAUDE_SURFACES = {
    "claude-desktop": ("VERIFIED", "Claude desktop app, Code tab (Claude Code)"),
    "cli": ("UNVERIFIED", "Claude Code CLI (`claude`) in a terminal"),
    "claude-vscode": ("UNVERIFIED", "Claude Code VS Code extension"),
    "claude-jetbrains": ("UNVERIFIED", "Claude Code JetBrains plugin"),
    "sdk-cli": ("UNSUPPORTED", "headless / print mode (no interactive human turn)"),
    "sdk-ts": ("UNSUPPORTED", "Agent SDK (no interactive human turn)"),
    "sdk-py": ("UNSUPPORTED", "Agent SDK (no interactive human turn)"),
    "remote": ("UNSUPPORTED", "Claude Code on the web / cloud session (not verified to run project hooks with the aidlc runtime)"),
}

EVENT_RE = re.compile(r"^\*\*Event\*\*:\s*([A-Z_]+)\s*$", re.M)
FIELD_RE = re.compile(r"^\*\*([^*]+)\*\*:\s?(.*)$", re.M)


def _semver(v: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", v)
    return tuple(int(x) for x in m.groups()) if m else None


# --------------------------------------------------------------------------
# Active workflow + ledger parsing (pure functions; unit-tested)
# --------------------------------------------------------------------------

def resolve_active_intent(root: pathlib.Path):
    """Return (intent_dir, error). Follows aidlc/active-space and the space's
    intents/active-intent cursor exactly; never guesses another workflow."""
    aidlc = root / "aidlc"
    space_file = aidlc / "active-space"
    space = space_file.read_text(encoding="utf-8").strip() if space_file.is_file() else "default"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", space or ""):
        return None, f"malformed active-space cursor: {space!r}"
    cursor = aidlc / "spaces" / space / "intents" / "active-intent"
    if not cursor.is_file():
        return None, f"no active workflow: {cursor.relative_to(root)} is missing (start one with /aidlc)"
    name = cursor.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return None, f"malformed active-intent cursor: {name!r}"
    intent_dir = aidlc / "spaces" / space / "intents" / name
    if not intent_dir.is_dir():
        return None, f"active-intent cursor points at a missing workflow record: {name}"
    return intent_dir, None


def parse_ledger(text: str):
    """Parse one audit shard into a list of event dicts. Raises ValueError on
    malformed evidence (an event block without a valid timestamp)."""
    events = []
    for block in re.split(r"\n---\n", text):
        if not EVENT_RE.search(block):
            continue
        fields = {k.strip(): v.strip() for k, v in FIELD_RE.findall(block)}
        ts = fields.get("Timestamp", "")
        if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ts):
            raise ValueError(f"event {fields.get('Event')} has a missing or malformed Timestamp: {ts!r}")
        events.append(fields)
    return events


def load_intent_events(intent_dir: pathlib.Path):
    """Read every audit shard of ONE workflow. Returns (events, error)."""
    audit = intent_dir / "audit"
    shards = sorted(audit.glob("*.md")) if audit.is_dir() else []
    if not shards:
        return [], f"no audit ledger in {intent_dir.name}/audit/"
    events = []
    for shard in shards:
        try:
            for i, e in enumerate(parse_ledger(shard.read_text(encoding="utf-8", errors="strict"))):
                e["_order"] = (e["Timestamp"], shard.name, i)
                events.append(e)
        except (ValueError, UnicodeDecodeError) as exc:
            return [], f"malformed ledger {shard.name}: {exc}"
    events.sort(key=lambda e: e["_order"])
    return events, None


# Claude Code delivers a finished sub-agent's report to the parent session as a
# queued prompt, which fires UserPromptSubmit, so the human-turn hook can record
# a HUMAN_TURN that no person caused. Hook releases that classify the prompt
# record an Origin field (upstream AI-DLC writes "person"; a host's turn becomes
# a separate HOST_TURN event, which never backs anything here); older ledgers
# have no Origin, and there a HUMAN_TURN landing within HANDBACK_WINDOW_S after
# a SUBAGENT_COMPLETED is treated as a hand-back.
HANDBACK_WINDOW_S = 2
HUMAN_ORIGINS = {"person", "prompt", "question-picker"}
NON_HUMAN_ORIGINS = {"host", "harness-envelope", "subagent-handback"}
# Gate resolutions the engine's presence gate consumes (aidlc-lib.ts
# GATE_RESOLUTION_EVENTS); a HUMAN_TURN backs at most the next one.
GATE_RESOLUTION_EVENTS = {
    "GATE_APPROVED", "GATE_REJECTED", "QUESTION_ANSWERED", "SUMMARY_CONFIRMATION_RECORDED",
    "VERIFICATION_COMMAND_RECORDED", "CONSTRUCTION_POLICY_RECORDED", "PLAN_APPROVAL_RECORDED",
}


def _epoch(ts: str) -> float:
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc).timestamp()


def classify_human_turns(events):
    """Mark each HUMAN_TURN with _human=True/False. An explicit Origin decides;
    without one, a turn at or up to HANDBACK_WINDOW_S after a SUBAGENT_COMPLETED
    (and ordered after it) is a suspected hand-back, never human backing."""
    handbacks = [e for e in events if e.get("Event") == "SUBAGENT_COMPLETED"]
    for e in events:
        if e.get("Event") != "HUMAN_TURN":
            continue
        origin = e.get("Origin", "").strip().lower()
        if origin in NON_HUMAN_ORIGINS:
            e["_human"] = False
        elif origin in HUMAN_ORIGINS:
            e["_human"] = True
        else:
            t = _epoch(e["Timestamp"])
            e["_human"] = not any(
                s["_order"] < e["_order"] and 0 <= t - _epoch(s["Timestamp"]) <= HANDBACK_WINDOW_S
                for s in handbacks)


def _approval_sensitive(events):
    """Yield (event, kind) for every event a human turn must back: plan
    approvals (protected), stage approvals and Request Changes (presence-gated),
    and switches to autonomous Construction (presence-gated). Gate decisions
    the engine took autonomously after a human-backed autonomy grant carry no
    User Input and are exempt."""
    autonomous = False
    for e in events:
        ev = e.get("Event")
        if ev == "AUTONOMY_MODE_SET":
            mode = e.get("Mode", "").strip().lower()
            if mode == "autonomous":
                yield e, "autonomous-mode switch"
            autonomous = mode == "autonomous"
        elif ev == "PLAN_APPROVAL_RECORDED":
            yield e, "plan approval"
        elif ev in ("GATE_APPROVED", "GATE_REJECTED"):
            if autonomous and not e.get("User Input"):
                continue
            yield e, "stage approval" if ev == "GATE_APPROVED" else "Request Changes"


def check_human_turn_evidence(events):
    """Return (ok, detail). Requires at least one human HUMAN_TURN with a session
    in this workflow's ledger, and every approval-sensitive event backed by a
    human HUMAN_TURN (hand-back turns never count; a genuine turn is accepted
    even when hand-back turns sit beside it):
      - PLAN_APPROVAL_RECORDED: a same-session turn after its plan-approval
        prompt (DECISION_RECORDED, checkpoint plan-approval);
      - GATE_APPROVED, GATE_REJECTED, AUTONOMY_MODE_SET autonomous: a turn
        after the previous gate resolution (same session when the event names
        one)."""
    turns = [e for e in events if e.get("Event") == "HUMAN_TURN"]
    if not turns:
        return False, "no HUMAN_TURN recorded in the active workflow (hooks not executing, or no human prompt yet)"
    if any(not e.get("Session") for e in turns):
        return False, "malformed HUMAN_TURN evidence: event without a Session"
    try:
        classify_human_turns(events)
    except ValueError as exc:
        return False, f"malformed ledger timestamp: {exc}"
    human = [t for t in turns if t["_human"]]
    if not human:
        return False, ("every HUMAN_TURN in the active workflow coincides with a sub-agent hand-back; "
                       "no genuine human turn is recorded")
    checked = {}
    for e, kind in _approval_sensitive(events):
        session = e.get("Session")
        if kind == "plan approval":
            if not session:
                return False, f"malformed PLAN_APPROVAL_RECORDED at {e['Timestamp']}: no Session"
            prompts = [p for p in events if p.get("Event") == "DECISION_RECORDED"
                       and "plan" in p.get("Checkpoint", "").lower()
                       and p["_order"] <= e["_order"]]
            floor = prompts[-1]["_order"] if prompts else ("",)
            window = "after its approval prompt"
        else:
            prior = [r for r in events if r.get("Event") in GATE_RESOLUTION_EVENTS and r["_order"] < e["_order"]]
            floor = prior[-1]["_order"] if prior else ("",)
            window = "since the previous gate resolution"
        candidates = [t for t in turns if floor <= t["_order"] <= e["_order"]
                      and (not session or t.get("Session") == session)]
        if not any(t["_human"] for t in candidates):
            if candidates:
                return False, (f"{e['Event']} ({kind}) at {e['Timestamp']} is backed only by HUMAN_TURN "
                               f"events that coincide with sub-agent hand-backs {window}")
            return False, (f"{e['Event']} ({kind}) at {e['Timestamp']} is not preceded by a HUMAN_TURN"
                           f"{' from the same session' if session else ''} {window}")
        checked[kind] = checked.get(kind, 0) + 1
    sessions = len({t["Session"] for t in turns})
    suspected = len(turns) - len(human)
    summary = ", ".join(f"{n} {k}(s)" for k, n in checked.items()) or "no approval-sensitive events"
    return True, (f"{len(turns)} HUMAN_TURN event(s) from {sessions} session(s) in the active workflow "
                  f"({suspected} excluded as sub-agent hand-backs); {summary}, each backed by a human turn "
                  f"(plan approvals by a same-session HUMAN_TURN)")


# --------------------------------------------------------------------------
# Claude configuration checks (pure functions; unit-tested)
# --------------------------------------------------------------------------

def _load_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def missing_claude_hooks(settings: dict):
    """Return the mandatory hooks absent from a Claude settings dict."""
    hooks = (settings or {}).get("hooks", {}) or {}
    missing = []
    for event, matcher, command in CLAUDE_MANDATORY_HOOKS:
        found = False
        for entry in hooks.get(event, []) or []:
            m = entry.get("matcher") or ""
            if matcher and matcher not in m.split("|") and m not in ("", "*"):
                continue
            if any((h or {}).get("command", "").strip() == command for h in entry.get("hooks", []) or []):
                found = True
                break
        if not found:
            missing.append(f"{event}[{matcher or '*'}] {command}")
    return missing


def hooks_disabled_by(settings_files):
    """Return the settings files (path, dict) that disable hooks."""
    return [str(p) for p, d in settings_files if isinstance(d, dict) and d.get("disableAllHooks") is True]


def detect_claude_surface(env):
    """Return (state, description, entrypoint)."""
    if env.get("CLAUDECODE") != "1":
        return "NOT_DETECTED", "not running inside a Claude Code session", None
    ep = env.get("CLAUDE_CODE_ENTRYPOINT", "")
    state, desc = CLAUDE_SURFACES.get(ep, ("UNVERIFIED", f"unrecognised Claude Code entrypoint '{ep or 'unset'}'"))
    return state, desc, ep or None


# --------------------------------------------------------------------------
# Check runner
# --------------------------------------------------------------------------

def _run_aidlc(args, cwd):
    aidlc = shutil.which("aidlc")
    if not aidlc:
        return None
    try:
        return subprocess.run([aidlc, *args], capture_output=True, text=True, timeout=120, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return None


def run_checks(tool: str, root: pathlib.Path, require_human_turn: bool, mode: str = "setup",
               env=None, run_aidlc=_run_aidlc, home: pathlib.Path | None = None) -> list[dict]:
    env = os.environ if env is None else env
    home = pathlib.Path.home() if home is None else home
    checks: list[dict] = []

    def add(name, status, detail, required=True):
        checks.append({"name": name, "status": status, "detail": detail, "required": required})

    cfg = SUPPORTED_TOOLS[tool]

    # 1. aidlc runtime present + version within policy
    out = run_aidlc(["version"], root)
    if out is None:
        add("aidlc-runtime", "FAIL", "`aidlc` not found on PATH (or failed to run)")
    else:
        ver = _semver(out.stdout + out.stderr)
        policy = _load_json(root / "docs" / "engineering-standard" / "framework-version.json")
        if ver and policy:
            lo, hi = _semver(policy["min_supported"]), _semver(policy["max_supported"])
            vs = ".".join(map(str, ver))
            if lo <= ver <= hi and vs not in policy.get("blocked", []):
                add("aidlc-runtime", "PASS", f"aidlc {vs} within policy window")
            else:
                add("aidlc-runtime", "FAIL", f"aidlc {vs} outside policy window "
                    f"[{policy['min_supported']}, {policy['max_supported']}]")
        else:
            add("aidlc-runtime", "FAIL", "could not resolve aidlc version or version policy")

    # 2. engine directory + agent present (installed harness)
    engine_dir = root / cfg["engine_dir"]
    add("engine-dir", "PASS" if engine_dir.is_dir() else "FAIL",
        f"{cfg['engine_dir']} {'present' if engine_dir.is_dir() else 'missing — run the install in the adapter'}")
    agent = root / cfg["agent_file"]
    add("aidlc-agent", "PASS" if agent.is_file() else "FAIL",
        f"{cfg['agent_file']} {'present' if agent.is_file() else 'missing'}")

    # 3. mandatory approval hooks wired, and not disabled
    if cfg["hook_file"]:
        hook = root / cfg["hook_file"]
        if not hook.is_file():
            add("approval-hook", "FAIL", f"{cfg['hook_file']} missing — human Plan Approval cannot be recorded")
        else:
            text = hook.read_text(encoding="utf-8", errors="ignore")
            wired = "record-human-turn" in text and "promptSubmit" in text
            add("approval-hook", "PASS" if wired else "FAIL",
                "prompt-submit human-turn hook present and wired" if wired
                else "approval hook present but not wired to promptSubmit/record-human-turn")
    else:
        settings = _load_json(root / ".claude" / "settings.json")
        if settings is None:
            add("approval-hook", "FAIL", ".claude/settings.json missing or not valid JSON")
        else:
            missing = missing_claude_hooks(settings)
            add("approval-hook", "FAIL" if missing else "PASS",
                ("mandatory hooks missing: " + "; ".join(missing)) if missing
                else f"all {len(CLAUDE_MANDATORY_HOOKS)} mandatory AI-DLC hooks wired in .claude/settings.json")
        layers = [(p, _load_json(p)) for p in (
            root / ".claude" / "settings.json",
            root / ".claude" / "settings.local.json",
            home / ".claude" / "settings.json",
            pathlib.Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
            pathlib.Path("/etc/claude-code/managed-settings.json"),
        ) if p.is_file()]
        disabled = hooks_disabled_by(layers)
        add("hooks-not-disabled", "FAIL" if disabled else "PASS",
            ("disableAllHooks is set in: " + ", ".join(disabled)) if disabled
            else "no Claude settings layer sets disableAllHooks")
        managed = [p for p, d in layers if "managed-settings" in str(p) and isinstance(d, dict)
                   and d.get("allowManagedHooksOnly") is True]
        add("managed-hook-policy", "FAIL" if managed else "PASS",
            ("organization policy allows managed hooks only (project AI-DLC hooks will not run): "
             + ", ".join(map(str, managed))) if managed
            else "no managed policy restricting project hooks detected")

    unattended = env.get("AIDLC_UNATTENDED", "")
    add("attended-mode", "FAIL" if unattended else "PASS",
        "AIDLC_UNATTENDED is set — human-presence checkpoints would be suppressed" if unattended
        else "AIDLC_UNATTENDED is not set")

    # 4. isolation: no inherited protected runtime state (fresh-clone check)
    leaks = [rel for rel in ["aidlc/.aidlc-sessions", "aidlc/.aidlc-clone-id"] if (root / rel).exists()]
    is_setup = mode == "setup" and not require_human_turn
    add("fresh-clone-isolation", "FAIL" if leaks else "PASS",
        (("inherited protected state present: " + ", ".join(leaks)) if leaks
         else "no inherited sessions/clone-id in the working tree")
        + ("" if is_setup else " (informational after the first governed session)"),
        required=is_setup)

    # 5. framework integrity / hook execution as reported by the runtime
    doc = run_aidlc(["doctor"], root)
    if doc is None:
        add("aidlc-doctor", "FAIL", "`aidlc doctor` could not run")
    else:
        text = doc.stdout + doc.stderr
        problems = re.search(r"(\d+) problems?", text)
        never = "Hooks have never executed" in text
        n = int(problems.group(1)) if problems else -1
        ok = n == 0 and not never
        add("aidlc-doctor", "PASS" if ok else "FAIL",
            "aidlc doctor: 0 problems" if ok else
            ("aidlc doctor reports hooks have never executed" if never
             else f"aidlc doctor reports {n if n >= 0 else 'unparsed'} problem(s)"))

    # 6. execution surface + hook execution evidence (inside the session)
    if mode == "session" or require_human_turn:
        if tool == "claude-code":
            state, desc, ep = detect_claude_surface(env)
            add("execution-surface", "PASS" if state in ("VERIFIED", "UNVERIFIED") else "FAIL",
                f"{state}: {desc}" + (" — run this preflight from the Claude Code session's shell tool"
                                       if state == "NOT_DETECTED" else ""))
        intent_dir, err = resolve_active_intent(root)
        if err:
            add("active-workflow", "FAIL", err)
        else:
            add("active-workflow", "PASS", f"active workflow: {intent_dir.name}")
            events, err = load_intent_events(intent_dir)
            if err:
                add("human-turn-recorded", "FAIL", err)
            elif mode == "session" and not require_human_turn:
                sid = env.get("CLAUDE_CODE_SESSION_ID") if tool == "claude-code" else None
                turns = [e for e in events if e.get("Event") == "HUMAN_TURN"
                         and (sid is None or e.get("Session") == sid)]
                add("human-turn-recorded", "PASS" if turns else "FAIL",
                    f"{len(turns)} HUMAN_TURN event(s) recorded for this session in the active workflow"
                    if turns else "no HUMAN_TURN for this session in the active workflow — the "
                    "human-turn hook is not executing (approve hooks, fully restart, send a prompt)")
            else:
                ok, detail = check_human_turn_evidence(events)
                add("human-turn-recorded", "PASS" if ok else "FAIL", detail)

    return checks


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AICC AI-DLC preflight diagnostics.")
    parser.add_argument("--tool", required=True, choices=sorted(SUPPORTED_TOOLS))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--mode", choices=["setup", "session"], default="setup")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-human-turn", action="store_true",
                        help="require same-session HUMAN_TURN evidence for every plan approval in the active workflow")
    args = parser.parse_args(argv)

    checks = run_checks(args.tool, pathlib.Path(args.repo_root).resolve(), args.require_human_turn, args.mode)
    failed_required = [c for c in checks if c["required"] and c["status"] != "PASS"]

    if args.json:
        print(json.dumps({"tool": args.tool, "mode": args.mode, "require_human_turn": args.require_human_turn,
                          "checks": checks, "ok": not failed_required}, indent=2))
    else:
        print(f"AICC preflight — {args.tool} (mode: {args.mode}"
              f"{', require-human-turn' if args.require_human_turn else ''})")
        for c in checks:
            mark = {"PASS": "ok  ", "FAIL": "FAIL"}.get(c["status"], c["status"])
            opt = "" if c["required"] else " [informational]"
            print(f"  [{mark}] {c['name']}: {c['detail']}{opt}")
        required = [c for c in checks if c["required"]]
        print(f"\n{'PASS' if not failed_required else 'FAIL'}: "
              f"{len(required) - len(failed_required)}/{len(required)} required checks passed")

    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
