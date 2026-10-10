# AICC Engineering Governance Policy

Status: Draft (pending AICC maintainer approval via pull request)
Applies to: every repository that adopts the AICC Multi-IDE Engineering Standard
Version: 1.0.0

## 1. Purpose

AICC runs the AWS AI-DLC (AI-Driven Development Life Cycle) across multiple AI
coding environments. This policy defines **one** engineering bar that holds
regardless of which validated tool an engineer uses, so that work is
reproducible, auditable, and comparable across tools. It is deliberately
**IDE-independent**: shared governance, the evidence contract, and GitHub
enforcement never depend on any single tool's hooks or internals.

## 2. Core principles

1. **Tool-independence.** Shared policy, the evidence schema, and CI are
   tool-agnostic. Each supported tool has a *separate* onboarding adapter
   (`docs/engineering-standard/onboarding/adapters/`). No shared rule is built
   around one tool's hook, path, or runtime detail.
2. **Human control at gates.** Every AI-DLC stage except bootstrap
   initialization requires an explicit human approval. Plan Approval before
   application code generation is mandatory and must be a *genuine, recorded*
   human turn (see §4).
3. **Evidence over assertion.** A claim of conformance is only as good as the
   committed evidence that supports it. CI validates committed evidence only.
4. **Honesty about what CI can prove.** GitHub CI cannot read a tool's private
   engine state, so it never claims to have verified protected human-approval
   receipts. It verifies framework integrity, required artifacts, test results,
   and sensitive-file exclusions — and says exactly that (see §5).
5. **Isolation per engineer.** Each engineer starts a NEW intent without
   inheriting another engineer's session, approval receipts, local paths, or
   protected runtime state (see §3).
6. **Portability.** No hardcoded personal paths, tokens, usernames, or account
   identifiers anywhere in the standard. The solution is portable to any
   corporate GitHub organization, including Huron's.

## 3. Isolation requirements

- A fresh clone plus `aidlc config --harness <tool>` produces a clean workspace
  with no copied sessions, receipts, cursors, or `.aidlc-engine/` state.
- Per-user cursors, per-clone audit-shard tokens, and session directories are
  git-ignored and never shared (enforced by the sensitive-file policy and the
  shipped `.gitignore`).
- Preflight diagnostics (`scripts/preflight.py`) fail clearly if prior protected
  state is detected in a tree that is supposed to be a fresh clone.

## 4. Human Plan Approval (non-negotiable)

- The AI-DLC human-presence control records a `HUMAN_TURN` authority event only
  when a real human prompt flows through the tool's interactive prompt-submit
  hook. This event is minted with an uncopyable internal token; an agent cannot
  fabricate it.
- **Governed application code generation MUST NOT proceed without a genuine,
  recorded human Plan Approval.** If the prompt-submit hook is not operating in
  the engineer's environment, the lifecycle is blocked at the gate by design.
  Bypassing, faking, or working around this control is prohibited and is a
  certification failure.
- Preflight diagnostics verify the prompt-submit hook is wired and that a
  `HUMAN_TURN` can be recorded in the engineer's interactive session before
  Construction begins.

## 5. What GitHub CI enforces

CI (`.github/workflows/engineering-standard-validation.yml`) validates, over
committed files only:

| Check | Script | What it proves |
|-------|--------|----------------|
| Framework integrity | `scripts/check_framework_integrity.py` | Evidence declares a framework version inside the supported window and the schema/exporter it depends on are committed |
| Required artifacts | `scripts/check_required_artifacts.py` | Every mandated standard deliverable is present |
| Evidence validity | `engineering-hub/evidence/exporter/validate_evidence.py` | Any committed evidence manifest conforms to the contract and its artifact hashes match |
| Test results | `engineering-hub/evidence/exporter/test_evidence.py` | The contract's positive/negative fixtures pass |
| Sensitive-file exclusions | `scripts/check_sensitive_files.py` | No secrets, private engine state, or machine-local artifacts are committed |

CI explicitly does **not** assert that protected human-approval receipts were
verified. The evidence contract encodes this: any `approvals` block is
`verifiable_by_ci: false`.

## 6. Change control

- This standard's shared policies, schemas, and enforcement change only via a
  pull request reviewed by the owners listed in `.github/CODEOWNERS`.
- Branch protection (documented in `04-branch-protection.md`) requires the CI
  validation workflow to pass and at least one CODEOWNER review before merge.
- The standardization work itself runs under AI-DLC Guard Policy **strict**: a
  changed input after an approval reopens that approval.

### 6.1 Owner-authorized personal-repository pilot exception

This exception is narrow and temporary. It applies **only** to the personal
pilot repository `AICC_Unified`, and only while the `.github/CODEOWNERS` teams
do not exist there and branch protection cannot be enabled. It ends when the
repository moves to the corporate GitHub organization.

- The repository owner may authorize a pull request that changes this standard
  or a tool's certification status. The owner records the authorization as a
  comment on the pull request, naming the change and any accepted risks. An
  author cannot submit an approving GitHub review of their own pull request.
- An owner authorization is **not** an independent CODEOWNER review and must
  never be described as one. Every status it authorizes is labelled
  "owner-authorized pilot" in the tool registry `state_reason` and in the
  certification matrix.
- Every other requirement still applies: the certification suite (§7), green
  CI validation, and genuine human Plan Approval (§4).
- On migration to the corporate organization, the real CODEOWNERS must review
  every owner-authorized status before it is treated as independently reviewed.
- This exception was adopted under itself, by owner authorization on
  certification pull request #2. It has not been independently reviewed.

## 7. Certification

An environment is **certified** only when every row of its certification suite
(`docs/engineering-standard/certification/`) is PASS against a real run — not
because its configuration files exist. The certification matrix records PASS,
FAIL, or NOT TESTED per environment and never upgrades "configured" to
"certified" (see `certification/certification-matrix.md`).
