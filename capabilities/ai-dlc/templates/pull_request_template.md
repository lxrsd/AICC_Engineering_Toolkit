# Pull Request — AICC Multi-IDE Engineering Standard

## Summary

<!-- What does this change do, and why? -->

## Type of change

- [ ] Standard governance / policy
- [ ] Evidence contract / exporter / schema
- [ ] Onboarding adapter (name the tool: ______) — kept separate from shared governance
- [ ] GitHub enforcement (CI / CODEOWNERS / branch protection docs)
- [ ] Certification suite / matrix
- [ ] Other: ______

## Tool-independence checklist

- [ ] No shared governance, schema, or CI rule depends on a single tool's hooks or internals
- [ ] Any tool-specific logic lives only in that tool's adapter under `docs/engineering-standard/onboarding/adapters/`

## Evidence & CI

- [ ] `engineering-standard-validation` CI is green
- [ ] Required artifacts present (`scripts/check_required_artifacts.py`)
- [ ] Evidence fixtures pass (`engineering-hub/evidence/exporter/test_evidence.py`)
- [ ] No secrets, private engine state, or machine-local files committed (`scripts/check_sensitive_files.py`)

## Approval integrity (do not fabricate)

- [ ] I did NOT fabricate any `HUMAN_TURN` / `GATE_APPROVED` event or bypass any protected guard
- [ ] If this PR claims an AI-DLC run, the evidence manifest's `approvals.verifiable_by_ci` is `false` (CI cannot verify protected receipts)

## Portability

- [ ] No hardcoded personal paths, tokens, usernames, or account identifiers
- [ ] Any `ORG/REPO`/team references resolve at runtime or are documented placeholders

## Certification status

<!-- State the certification status honestly. "Configured" is not "certified". -->
- Environment(s) affected:
- Certification matrix updated? (`docs/engineering-standard/certification/certification-matrix.md`)
