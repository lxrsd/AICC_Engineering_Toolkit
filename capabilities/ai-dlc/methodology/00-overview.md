# AICC Multi-IDE Engineering Standard — Overview

Version: 1.0.0
Status: **Technically validated; AI-DLC execution NOT certified** (see
`certification/certification-matrix.md` and `certification/approval-hook-issue.md`).

## What this is

One reusable, IDE-independent AWS AI-DLC engineering standard for the AICC
Unified Center and Engineering Hub. It lets every AICC engineer clone the
approved repository and run the full AI-DLC lifecycle — including genuine
human-approved AI code generation — in any officially validated AI coding
environment, while GitHub enforces one shared bar.

Supported environments: **Kiro CLI** (validated), **Claude Code** (next
certification pilot), **Kiro IDE** (separate track, blocked by an approval
defect), **Cursor** (future).

## Deliverables and where they live

| # | Deliverable | Location |
|---|-------------|----------|
| 1 | Engineering governance policy | `01-governance-policy.md` |
| 1 | Framework-version policy | `02-framework-version-policy.md` + `framework-version.json` |
| 2 | Reproducible onboarding (shared) | `onboarding/README.md` |
| 2 | Tool adapters (kept separate) | `onboarding/adapters/{kiro-cli,kiro-ide,claude-code}.md` |
| 3 | Evidence contract + schema | `03-evidence-contract.md`, `../../engineering-hub/evidence/schema/evidence-manifest.schema.json` |
| 3 | Evidence exporter + validator | `../../engineering-hub/evidence/exporter/{export,validate}_evidence.py` |
| 4 | GitHub Actions validation | `../../.github/workflows/engineering-standard-validation.yml` |
| 5 | CODEOWNERS + PR templates | `../../.github/CODEOWNERS`, `../../.github/pull_request_template.md`, `../../.github/PULL_REQUEST_TEMPLATE/` |
| 6 | Positive + negative CI fixtures | `../../engineering-hub/evidence/fixtures/`, `../../engineering-hub/evidence/exporter/test_evidence.py` |
| 7 | Documented branch protection | `04-branch-protection.md` + `branch-protection.sample.json` |
| 8 | Evidence Explorer integration spec | `../../engineering-hub/evidence-explorer/integration-spec.md` |

Supporting: preflight diagnostics (`../../scripts/preflight.py`), CI checks
(`../../scripts/check_*.py`), certification suite + matrix
(`certification/`).

## Design guarantees

- **IDE-independent core.** Governance, evidence schema, and GitHub enforcement
  never depend on any single tool. Tool specifics live only in adapters.
- **Genuine human approval.** Governed code generation requires a real,
  recorded `HUMAN_TURN` Plan Approval; the control cannot be fabricated and is
  not bypassed.
- **Honest CI.** CI validates committed evidence only and never claims to verify
  protected approval receipts it cannot access.
- **Isolation.** Each engineer starts clean; no inherited sessions, receipts,
  paths, or protected state.
- **Portable.** No hardcoded paths, tokens, usernames, or account identifiers;
  ports to Huron's corporate GitHub.

## Current status (honest)

The shared technical standard is validated by the automated suite (see the
handoff report). The governed AI-DLC lifecycle is **NOT certified** in this
session because the `HUMAN_TURN` approval event was not recorded by the
environment used to drive the run; the root cause and supported remediation are
in `certification/approval-hook-issue.md`. No approval was fabricated.

## Run the automated validation

```bash
python3 engineering-hub/evidence/exporter/test_evidence.py
python3 scripts/check_required_artifacts.py --repo-root .
python3 scripts/check_sensitive_files.py --repo-root .
python3 scripts/check_framework_integrity.py \
  --manifest engineering-hub/evidence/fixtures/positive/evidence-manifest.json --repo-root .
```
