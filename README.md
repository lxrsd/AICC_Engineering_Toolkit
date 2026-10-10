# AICC Engineering Toolkit

Engineer-facing tools and standards for AICC's AI-Driven Development Life Cycle
(AI-DLC). **You do not need access to any private AICC repository to use this.**

This toolkit distributes AICC-authored methodology, tool adapters, validators,
and templates for running the governed AI-DLC lifecycle in a supported AI
coding tool. It does **not** contain or redistribute the AI-DLC runtime itself —
that comes from its own authorized source (the `aidlc` CLI, see below).

## What's here

```
capabilities/
  ai-dlc/
    methodology/   AI-DLC lifecycle, governance, evidence contract, onboarding
    adapters/      per-tool setup: kiro-cli, claude-code, cursor (pending)
    templates/     PR template, CODEOWNERS sample, branch-protection sample
    validators/    evidence exporter + validator, schema, fixtures, preflight, checks,
                   and the sanitized public certification registry
  factory-ai/      FUTURE placeholder — not implemented, not installable
installer/         install.py — set up a capability for your tool
releases/          versioned release notes
```

## Certification status (public, sanitized)

Source of truth: `capabilities/ai-dlc/validators/public-registry.json`, a
sanitized projection of AICC's private authoritative registry (no internal
reasons, evidence, or receipts are published).

| Tool | Status |
|------|--------|
| Kiro CLI | **CERTIFIED** — Owner-Authorized Pilot (AI-DLC 2.10.0) |
| Claude Code | **CERTIFIED** — Owner-Authorized Pilot (AI-DLC 2.10.0) |
| Kiro IDE | FAILED (not an install option) |
| Cursor | PENDING (future candidate; documentation only) |

Owner-authorized pilot certifications are valid for the stated framework
version and are subject to corporate review on migration. Only **CERTIFIED**
tools are offered as approved installation options.

## Prerequisites

- Python 3.9+
- Your AI coding tool (Kiro CLI or Claude Code)
- The **AI-DLC runtime** (`aidlc` CLI) on your PATH, obtained from its authorized
  source. This toolkit does not bundle it. Verify with `aidlc version`
  (expected runtime 2.10.0, per `capabilities/ai-dlc/methodology/framework-version.json`).

## Quick start

```bash
# See capabilities and which tools are approved (certified):
python3 installer/install.py --list

# Install the AI-DLC standard for your tool into YOUR project:
python3 installer/install.py --capability ai-dlc --tool kiro-cli   --target /path/to/your/project
python3 installer/install.py --capability ai-dlc --tool claude-code --target /path/to/your/project
```

The installer is non-destructive (writes under `<project>/.aicc/ai-dlc/`),
idempotent, drives the runtime through the authorized `aidlc` CLI if present,
and runs post-install validation. Follow your tool's adapter README
(`capabilities/ai-dlc/adapters/<tool>/README.md`) for the governed-lifecycle and
approval-gate specifics.

## Validate the toolkit itself

```bash
python3 capabilities/ai-dlc/validators/test_evidence.py        # evidence contract fixtures
python3 installer/test_independence.py                         # standalone + no-private-dependency checks
```

## Scope and honesty

- Certified = proved the full governed lifecycle end-to-end in a real run
  (owner-authorized pilot). FAILED / PENDING / future states are shown honestly
  and never upgraded by configuration presence.
- CI and validators check committed evidence only; they never claim to verify
  protected human-approval receipts.
- Factory AI is a reserved future placeholder with no implementation.
