# AICC Universal Developer Onboarding Guide

Version: 1.0.0

One guide for every AICC engineer, independent of which AI coding tool you use.
It covers the full path from cloning the repository to submitting evidence. Your
tool's specifics live in a separate adapter (`adapters/<tool>.md`); this guide is
the shared spine they all plug into.

## 0. Eligibility — is your tool supported?

Check `../tool-registry.json`. A tool is usable for a governed run only when its
registry `state` is CERTIFIED (or an explicitly evidence-accepting PENDING
pilot). States: CERTIFIED, FAILED, PENDING, UNSUPPORTED. Presence of config
files is never certification. To add a new tool, see
`tool-adapter-specification.md` §7.

## 1. Clone the repository (fresh, isolated)

```bash
git clone <approved-repo-url> aicc-work && cd aicc-work
```

Do not copy another engineer's working tree, `aidlc/.aidlc-sessions/`,
`aidlc/.aidlc-clone-id`, cursors, or `.aidlc-engine/` state. Each engineer
starts clean.

## 2. Install the framework for your tool

Follow your adapter's install step (e.g. `aidlc config --harness <tool> --yes`).
A correct install shows `merge=0, preserve=0` and `aidlc doctor` reports 0
problems. This copies no sessions, receipts, cursors, or engine state.

## 3. Configure

The install wires your tool's AI-DLC agent and hooks. Confirm the framework
version satisfies the policy (`../framework-version.json`).

## 4. Preflight checks (fail early, fail clearly)

```bash
python3 scripts/preflight.py --tool <id>
```

It fails clearly if the AI-DLC agent, the human-prompt hook, the framework
version, or the approval machinery are missing or misconfigured, or if a tree
that should be a fresh clone still carries protected state. Before governed
code generation, also run:

```bash
python3 scripts/preflight.py --tool <id> --require-human-turn
```

which passes only once a genuine human approval turn can be recorded.

## 5. Run the AI-DLC lifecycle (in the interactive agent)

Launch your tool's interactive AI-DLC agent (see your adapter), then start a NEW
intent and work the stages:

1. Describe the build and capture intent
2. Requirements and design
3. **Genuine human Plan Approval** — approve as a real person at the gate. Never
   fabricated; the control records a protected `HUMAN_TURN`.
4. AI code generation (only after valid approval)
5. Build and automated tests
6. Independent review
7. Traceability intent -> design -> code -> tests

## 6. Genuine human approvals (why this matters)

The approval control records a `HUMAN_TURN` authority event only when a real
human prompt flows through your tool's prompt-submit hook, using an uncopyable
token. If you drive the engine from outside that interactive seam, no
`HUMAN_TURN` is recorded and the engine refuses approvals — by design. Never
bypass or fake this; launch the interactive agent instead.

## 7. Export sanitized evidence

Your adapter emits a neutral run descriptor; then:

```bash
python3 engineering-hub/evidence/exporter/export_evidence.py \
  --descriptor <run-descriptor.json> --repo-root . --out evidence-manifest.json
python3 engineering-hub/evidence/exporter/validate_evidence.py \
  evidence-manifest.json --repo-root . --check-artifacts
python3 scripts/check_sensitive_files.py --repo-root .
```

## 8. Submit for validation (pull request)

Open a pull request. The `engineering-standard-validation` workflow checks
framework integrity, required artifacts, evidence validity, test results,
sensitive-file exclusions, and the tool registry. CI validates committed
evidence only and never claims to verify protected approval receipts.

## 9. Portability

Every command resolves the repository and user context from your own clone and
environment. Nothing here hardcodes a path, token, username, or account, so this
ports unchanged to Huron's corporate GitHub.
