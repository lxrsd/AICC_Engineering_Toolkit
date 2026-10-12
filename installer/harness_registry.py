#!/usr/bin/env python3
"""AICC Engineering Toolkit — centralized harness registry.

ONE source of truth describing every official AWS Labs AI-DLC harness the
Toolkit supports. install.py, aidlc_activation.py, and the bootstrappers all
read this registry instead of hardcoding per-tool facts.

All per-harness facts here are taken from the OFFICIAL upstream guide
(https://awslabs.github.io/aidlc-workflows/guide/harnesses/), not invented:

  Harness        config id   invoke    onboarding surface the runtime generates
  -------------  ----------  --------  -----------------------------------------
  Claude Code    claude      /aidlc    .claude/CLAUDE.md (full onboarding)
  Kiro CLI       kiro        /aidlc    .kiro/steering/aidlc-onboarding.md
  Kiro IDE       kiro-ide    /aidlc    .kiro/steering/aidlc-onboarding.md
  Codex CLI      codex       $aidlc    .codex/onboarding.md + .codex/config.toml
  Cursor         cursor      /aidlc    .cursor/rules/aidlc-onboarding.mdc
  opencode       opencode    /aidlc    .aidlc/onboarding.md + .opencode/
  GitHub Copilot copilot     /aidlc    root AGENTS.md (full) + .github/

Coexistence (upstream): Kiro, Kiro IDE, Codex, Cursor, and opencode share the
harness-neutral root AGENTS.md block, so several can coexist in one project;
each needs its own distinct engine directory. Copilot's full root AGENTS.md
block is EXCLUSIVE, so Copilot does not co-reside with the others on the shared
root block.

The OFFICIAL runtime is a one-time machine prerequisite; its native installer
always ships every harness runtime, and `aidlc config --harness <id>` selects a
project's surface. We never copy/fork/recreate the methodology — the registry
only records how to drive and VERIFY the official runtime per harness.

Stdlib only; pure data + helpers (no side effects on import).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Invocation styles — Task 11: do not claim identical invocation across tools.
INVOKE_SLASH = "/aidlc"     # Claude, Kiro, Kiro IDE, Cursor, opencode, Copilot
INVOKE_DOLLAR = "$aidlc"    # Codex CLI


@dataclass(frozen=True)
class Harness:
    id: str                       # official `aidlc config --harness <id>` value
    display_name: str             # human-readable tool name
    detect_cli: tuple = ()        # executables that indicate the tool is installed
    is_editor: bool = False       # IDE/editor (not a PATH CLI we can shutil.which)
    invoke: str = INVOKE_SLASH    # how the engineer starts AI-DLC in-tool
    # Project-local engine surface the official runtime generates. Presence of
    # ANY of these (that the Toolkit did not itself write) VERIFIES config.
    engine_markers: tuple = ()
    # The native onboarding/instruction file the runtime writes (discovery).
    onboarding_file: str = ""
    # Shares the harness-neutral root AGENTS.md block with other harnesses?
    shares_root_agents: bool = True
    # Platform support + minimum tool versions (from upstream docs).
    platforms: tuple = ("darwin", "linux", "windows")
    min_version: str = ""
    requires_git_repo: bool = False
    notes: str = ""


# The seven officially supported harnesses.
HARNESSES: dict[str, Harness] = {
    "claude": Harness(
        id="claude", display_name="Claude Code",
        detect_cli=("claude",), invoke=INVOKE_SLASH,
        engine_markers=(".claude",),
        onboarding_file=".claude/CLAUDE.md",
        shares_root_agents=True,
    ),
    "kiro": Harness(
        id="kiro", display_name="Kiro CLI",
        detect_cli=("kiro-cli", "kiro"), invoke=INVOKE_SLASH,
        engine_markers=(".kiro/steering/aidlc-onboarding.md", ".kiro/hooks",
                        ".kiro/agents", ".kiro/settings"),
        onboarding_file=".kiro/steering/aidlc-onboarding.md",
        shares_root_agents=True, min_version="2.6",
        notes="v3 engine requires Kiro CLI >= 2.24.1.",
    ),
    "kiro-ide": Harness(
        id="kiro-ide", display_name="Kiro IDE",
        detect_cli=(), is_editor=True, invoke=INVOKE_SLASH,
        engine_markers=(".kiro/steering/aidlc-onboarding.md", ".kiro/hooks",
                        ".kiro/agents", ".kiro/settings"),
        onboarding_file=".kiro/steering/aidlc-onboarding.md",
        shares_root_agents=True, min_version="1.1.70",
        notes="Editor; CLI auto-detection not possible. Shares the .kiro engine with Kiro CLI.",
    ),
    "codex": Harness(
        id="codex", display_name="Codex CLI",
        detect_cli=("codex",), invoke=INVOKE_DOLLAR,
        engine_markers=(".codex/onboarding.md", ".codex/config.toml"),
        onboarding_file=".codex/onboarding.md",
        shares_root_agents=True, min_version="0.145.0", requires_git_repo=True,
        notes="Invokes with $aidlc (NOT /aidlc). Requires the project to be a git repo.",
    ),
    "cursor": Harness(
        id="cursor", display_name="Cursor",
        detect_cli=("cursor",), is_editor=True, invoke=INVOKE_SLASH,
        engine_markers=(".cursor/rules/aidlc-onboarding.mdc", ".cursor/rules"),
        onboarding_file=".cursor/rules/aidlc-onboarding.mdc",
        shares_root_agents=True,
        notes="IDE + CLI; native subagents/skills + hooks.json adapter.",
    ),
    "opencode": Harness(
        id="opencode", display_name="opencode",
        detect_cli=("opencode",), invoke=INVOKE_SLASH,
        engine_markers=(".aidlc/onboarding.md", ".opencode"),
        onboarding_file=".aidlc/onboarding.md",
        shares_root_agents=True, min_version="1.17",
        notes="Split .aidlc/ + .opencode/ layout with an adapter plugin.",
    ),
    "copilot": Harness(
        id="copilot", display_name="GitHub Copilot",
        detect_cli=("copilot",), invoke=INVOKE_SLASH,
        engine_markers=(".github/aidlc", ".github"),
        onboarding_file="AGENTS.md",
        shares_root_agents=False,   # Copilot's full root block is EXCLUSIVE
        min_version="1.0.74",
        notes="CLI >= 1.0.74 / VS Code >= 1.130. Full onboarding lives in the "
              "root AGENTS.md (exclusive); does not share the neutral root block.",
    ),
}

# Backwards-compatible aliases some callers still use (tool-id -> harness-id).
TOOL_ALIAS = {
    "claude-code": "claude",
    "kiro-cli": "kiro",
}


def resolve(harness_or_tool: str) -> Harness | None:
    """Resolve a harness id OR a legacy tool id to a Harness, or None."""
    key = TOOL_ALIAS.get(harness_or_tool, harness_or_tool)
    return HARNESSES.get(key)


def all_ids() -> list[str]:
    return list(HARNESSES.keys())


def shares_root_agents(harness_id: str) -> bool:
    h = HARNESSES.get(harness_id)
    return bool(h and h.shares_root_agents)


def can_coexist(a: str, b: str) -> bool:
    """Whether two harnesses may be configured in the same project at once,
    per upstream: all the root-block-sharing harnesses coexist; Copilot (whose
    full root AGENTS.md block is exclusive) does not co-reside with another."""
    if a == b:
        return True
    ha, hb = HARNESSES.get(a), HARNESSES.get(b)
    if not ha or not hb:
        return False
    return ha.shares_root_agents and hb.shares_root_agents
