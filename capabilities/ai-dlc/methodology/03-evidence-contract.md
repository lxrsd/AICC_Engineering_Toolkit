# AICC Evidence Contract (tool-independent)

Version: 1.0.0
Schema: `../../engineering-hub/evidence/schema/evidence-manifest.schema.json`
Exporter: `../../engineering-hub/evidence/exporter/export_evidence.py`
Validator: `../../engineering-hub/evidence/exporter/validate_evidence.py`

## 1. What this is

A single, tool-agnostic description of an AI-DLC run that any supported
environment (Kiro CLI, Kiro IDE, Claude Code, future Cursor) can emit and that
GitHub CI can validate over committed files. It makes evidence from different
tools comparable and reproducible.

## 2. Separation of concerns

```
  tool native state  --->  [ tool-specific onboarding adapter ]  --->  neutral run descriptor
                                                                              |
                                                                              v
                                             [ export_evidence.py (tool-agnostic) ]
                                                                              |
                                                                              v
                                                   evidence-manifest.json (the contract)
                                                                              |
                                                                              v
                               [ validate_evidence.py / GitHub CI ]  (committed files only)
```

- The **adapter** is the only tool-specific component. It maps a tool's native
  record into the neutral run descriptor (shape documented in
  `export_evidence.py`). Adapters live under `onboarding/adapters/` and are kept
  separate per tool.
- The **exporter** and **manifest** are tool-independent.
- The **validator** / CI read only committed files.

## 3. Manifest shape (summary)

| Field | Required | Notes |
|-------|----------|-------|
| `schema_version` | yes | `1.0.0` |
| `generated_at` | yes | UTC ISO-8601 `Z` |
| `tool` | yes | id / surface / adapter_version — the only tool-specific block |
| `framework` | yes | name / version (semver) / scope |
| `intent` | yes | id / title / guard_policy |
| `stages` | yes | per-stage status + produced artifacts |
| `tests` | yes | framework / total / passed / failed / results_path |
| `artifacts` | yes | content-addressed inventory (path + sha256 + kind) |
| `approvals` | optional | DECLARED, not verified — see §4 |

See the JSON Schema for exact rules.

## 4. The honesty rule (protected approval receipts)

Human Plan Approval and other gate approvals are recorded by the AI-DLC engine
as protected authority events (`HUMAN_TURN`, `GATE_APPROVED`) in private,
per-clone engine state. **GitHub CI cannot read that state.** Therefore:

- The optional `approvals` block is a *declaration* by the producing tool, not
  a verifiable proof.
- Its `verifiable_by_ci` field is constrained to `false` by the schema, and the
  validator's `honesty_check` rejects any manifest that sets it `true`.
- CI never prints or implies that it verified protected approval receipts.

This keeps the evidence truthful: CI validates what it can actually see
(committed artifacts, hashes, test results, exclusions) and makes no claim
about what it cannot.

## 5. Reproducibility

Every artifact is content-addressed by SHA-256. Running
`validate_evidence.py --check-artifacts` re-hashes each committed file and
fails on any mismatch, so a manifest cannot drift from the files it describes.

## 6. Portability

The contract references repo-relative paths only. It contains no machine
paths, tokens, usernames, or account identifiers.
