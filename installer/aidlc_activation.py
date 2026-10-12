#!/usr/bin/env python3
"""AICC Engineering Toolkit — automatic AI-DLC activation layer.

PROBLEM THIS SOLVES
-------------------
On a real Windows acceptance run, Claude Code read AGENTS.md and understood that
AI-DLC was required, but the project had only Kiro's configuration — no .claude/
engine, no active Claude intent — so a plain "build me X" request would NOT start
the governed AI-DLC workflow.

Two root causes, two layers of fix (both here):

1. INSTRUCTION DISCOVERY. Claude Code loads CLAUDE.md at the start of every
   session. Its default `claude-md-or-agents-md` behavior only falls back to
   AGENTS.md when the project has NO CLAUDE.md of its own. A project configured
   for Kiro can end up with a CLAUDE.md (or none) that doesn't point Claude at
   the shared AI-DLC activation rule. We therefore author:
     - AGENTS.md         : tool-neutral activation instruction (the single
                           source of truth; references the official methodology,
                           never duplicates it),
     - CLAUDE.md         : a THIN pointer that defers to AGENTS.md so Claude
                           always loads the activation rule (no methodology copy),
     - .kiro/steering/aicc-ai-dlc.md : a Kiro steering pointer to AGENTS.md.
   All three are written non-destructively and idempotently: existing files are
   never clobbered; our managed block is inserted/updated between sentinels, and
   the engineer's own content around it is preserved.

2. ENGINE ENFORCEMENT. Memory files guide but do not enforce; the runtime's
   harness hooks are what actually gate code generation behind requirements +
   human approval. configure_harness() drives the OFFICIAL runtime to build the
   harness surface for the selected tool and then VERIFIES the engine surface
   (.claude/ or .kiro/) actually exists — so the installer never claims a harness
   is wired when the runtime produced nothing.

SCOPE / HONESTY
---------------
This module NEVER copies, forks, or recreates AWS Labs AI-DLC methodology. The
instruction files it writes are short activation pointers to the official
runtime and the AICC-namespaced methodology already installed under
.aicc/ai-dlc/. Workbench is never required here. Stdlib only.
"""
from __future__ import annotations

import pathlib
import subprocess

# Managed-block sentinels. We only ever touch text BETWEEN these markers, so an
# engineer's own instructions in the same file are preserved on re-run.
BEGIN = "<!-- BEGIN AICC AI-DLC (managed; edit outside this block) -->"
END = "<!-- END AICC AI-DLC -->"

# Tool-neutral activation instruction. Deliberately short and imperative. It
# POINTS to the official methodology; it does not restate it.
AGENTS_BLOCK = f"""{BEGIN}
## AI-DLC is REQUIRED in this project

This project is governed by the **official AWS Labs AI-DLC** methodology,
configured by the AICC Engineering Toolkit. It applies to **every** AI coding
tool used here (Claude Code, Kiro CLI, or any other).

**When the engineer asks to build, add, or change application functionality
(for example: "Build me an Expense Tracker web application"), you MUST start the
official AI-DLC workflow instead of writing application code immediately.**

Specifically, before generating application code you must:

1. Capture the **intent** and produce **Requirements**.
2. Produce a **Design**.
3. Stop at the **human Plan Approval** gate — a real person approves the plan.
   Do not write application code until that approval is recorded.
4. Only then generate code, run build + tests, and produce evidence.

Do not skip the requirements or approval checkpoints, and do not fabricate an
approval. If the official AI-DLC engine/agent is available in your tool, run it
(e.g. the `/aidlc` command or your tool's AI-DLC agent) to drive these stages.

The methodology and governance live under `.aicc/ai-dlc/` in this project and in
the official runtime (`aidlc`). This file is an activation pointer, not a copy of
the methodology.
{END}
"""

CLAUDE_BLOCK = f"""{BEGIN}
## Project instructions: follow AGENTS.md (AI-DLC is required)

This project uses the **official AWS Labs AI-DLC** methodology for all AI coding
tools. The authoritative, tool-neutral instructions are in **`AGENTS.md`** at the
project root — read it and follow it.

In particular: when asked to build, add, or change application functionality,
**start the official AI-DLC workflow** (intent → requirements → design → human
Plan Approval → code → tests → evidence). Do **not** write application code
before the requirements are captured and a real human approves the plan.

See `AGENTS.md` for the full activation rule. (This file intentionally defers to
AGENTS.md and does not duplicate the methodology.)
{END}
"""

KIRO_STEERING_BLOCK = f"""{BEGIN}
---
inclusion: always
---
# AICC AI-DLC activation (Kiro)

This project is governed by the **official AWS Labs AI-DLC** methodology. The
authoritative, tool-neutral instructions are in `AGENTS.md` at the project root.

When asked to build, add, or change application functionality, start the official
AI-DLC workflow (intent → requirements → design → **human Plan Approval** → code →
tests → evidence) rather than writing application code immediately. Do not skip
the approval checkpoint. See `AGENTS.md`.
{END}
"""


def _write_managed(path: pathlib.Path, block: str, dry_run: bool) -> str:
    """Create or update ONLY our managed block in `path`, preserving any other
    content. Idempotent: re-running replaces the block in place, never appending
    a duplicate. Returns a human status line."""
    rel = path.name
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return f"{rel}: unreadable; left untouched (add the AI-DLC block manually)"
        if BEGIN in text and END in text:
            pre = text.split(BEGIN, 1)[0]
            post = text.split(END, 1)[1]
            new = pre + block.rstrip("\n") + post
            if new == text:
                return f"{rel}: AI-DLC activation block already present (no change)"
            if dry_run:
                return f"{rel}: DRY-RUN would refresh the AI-DLC activation block"
            path.write_text(new, encoding="utf-8")
            return f"{rel}: refreshed AI-DLC activation block (your other content preserved)"
        # File exists but has no managed block: append ours, keep their content.
        if dry_run:
            return f"{rel}: DRY-RUN would append the AI-DLC activation block (existing content preserved)"
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        path.write_text(text + sep + block, encoding="utf-8")
        return f"{rel}: appended AI-DLC activation block (your existing content preserved)"
    # New file.
    if dry_run:
        return f"{rel}: DRY-RUN would create with the AI-DLC activation block"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block, encoding="utf-8")
    return f"{rel}: created with the AI-DLC activation block"


def write_activation_instructions(target: pathlib.Path, harness: str, dry_run: bool) -> list[str]:
    """Author the tool-neutral AGENTS.md plus the discovery pointers each tool
    needs, non-destructively. Returns status lines.

    - AGENTS.md: always (the single source of truth).
    - CLAUDE.md: always a thin pointer — Claude loads CLAUDE.md every session,
      and when a CLAUDE.md exists Claude does NOT auto-fall back to AGENTS.md, so
      the pointer guarantees Claude still loads the activation rule. Written for
      BOTH harnesses so a later switch to Claude already has it.
    - .kiro/steering/aicc-ai-dlc.md: a Kiro steering pointer (always-included),
      written for both harnesses for the same forward-compatible reason.
    """
    lines = []
    lines.append(_write_managed(target / "AGENTS.md", AGENTS_BLOCK, dry_run))
    lines.append(_write_managed(target / "CLAUDE.md", CLAUDE_BLOCK, dry_run))
    lines.append(_write_managed(target / ".kiro" / "steering" / "aicc-ai-dlc.md",
                                KIRO_STEERING_BLOCK, dry_run))
    return lines


# ---------------------------------------------------------------------------
# Engine configuration + verification (official runtime; version-aware)
# ---------------------------------------------------------------------------

# The project-local engine surface each harness produces. Presence of one of
# these (beyond our own files) is how we VERIFY the runtime actually configured
# the harness — rather than trusting an exit code from a possibly no-op flag.
HARNESS_SURFACE = {
    "claude": [".claude"],
    "kiro": [".kiro"],
}


def _harness_configured(target: pathlib.Path, harness: str) -> bool:
    """True if the runtime's engine surface for `harness` exists in the project.

    For Kiro we require more than the bare .kiro/steering pointer this module
    writes: an engine surface means hooks/agents/settings the runtime generates.
    """
    if harness == "kiro":
        kiro = target / ".kiro"
        if not kiro.is_dir():
            return False
        # Our steering pointer alone is not an engine. Require some other Kiro
        # engine artifact (hooks/agents/settings/specs) to call it configured.
        engine_markers = ["hooks", "agents", "settings", "settings.json", "specs", "steering/aidlc"]
        for m in engine_markers:
            if (kiro / m).exists():
                return True
        # steering dir with files other than our single pointer also counts.
        steering = kiro / "steering"
        if steering.is_dir():
            others = [p for p in steering.iterdir() if p.name != "aicc-ai-dlc.md"]
            if others:
                return True
        return False
    if harness == "claude":
        return (target / ".claude").is_dir()
    return False


def configure_harness(aidlc_exe: str, target: pathlib.Path, harness: str,
                      dry_run: bool, run=subprocess.run) -> tuple[bool, str]:
    """Drive the OFFICIAL runtime to configure `harness` in `target`, then VERIFY
    the engine surface exists. Returns (configured, message).

    Version-aware: different aidlc releases expose harness selection differently.
    We attempt the known non-interactive invocations in order and stop at the
    first that leaves a verified engine surface. We NEVER claim success on a bare
    exit code — success means the surface is actually present. `run` is injected
    for testing (no real subprocess).
    """
    if dry_run:
        return (False, f"DRY-RUN: would configure the '{harness}' harness via the official runtime in {target}")

    # Already configured (idempotent / switch-safe): don't reconfigure, don't
    # disturb the other harness.
    if _harness_configured(target, harness):
        return (True, f"'{harness}' harness already configured (verified engine surface present)")

    # Candidate non-interactive invocations across runtime versions. Each is the
    # OFFICIAL cli; we do not reimplement it. Unknown flags on older versions are
    # harmless (ignored) — we rely on surface verification, not exit codes.
    attempts = [
        [aidlc_exe, "config", "--harness", harness, "--yes"],
        [aidlc_exe, "config", "harness", harness, "--yes"],
        [aidlc_exe, "config", "--harness", harness, "--non-interactive"],
    ]
    last_detail = ""
    for cmd in attempts:
        try:
            r = run(cmd, cwd=str(target), capture_output=True, text=True, timeout=180)
            last_detail = (getattr(r, "stderr", "") or getattr(r, "stdout", "") or "").strip()[:200]
        except Exception as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
            continue
        if _harness_configured(target, harness):
            return (True, f"configured '{harness}' harness via `{' '.join(cmd[1:])}` (engine surface verified)")

    # Nothing produced a verified surface. Be honest.
    return (False,
            f"could not confirm the '{harness}' engine surface was created by the installed runtime. "
            f"This runtime may need interactive `aidlc config` (run it in {target} and choose the "
            f"'{harness}' harness), or a newer release. Instruction files (AGENTS.md/CLAUDE.md) are in "
            f"place so the tool still knows AI-DLC is required."
            + (f" Last runtime output: {last_detail}" if last_detail else ""))
