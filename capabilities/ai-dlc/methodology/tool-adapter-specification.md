# AICC Tool-Adapter Specification (integration contract)

Version: 1.0.0

This is the reusable contract any AI coding environment implements to join the
AICC Multi-IDE Engineering Standard. It lets a new tool be onboarded through a
**separate adapter + certification** without changing the shared methodology,
schema, CI, or governance. Kiro CLI, Kiro IDE, Claude Code, and the Cursor
future candidate are all instances of this contract.

## 1. What an adapter is (and is not)

- An adapter is the ONLY tool-specific component. It maps a tool's native
  install, interactive session, and run record into the shared, tool-agnostic
  contract.
- An adapter does NOT fork or weaken shared governance, the evidence schema, CI,
  or the approval controls. Nothing shared may depend on one tool's hooks.

## 2. Required capabilities (a tool must provide all)

| # | Capability | How it is proven |
|---|------------|------------------|
| C1 | Isolated install from a fresh clone (no copied sessions/receipts/paths/state) | `aidlc config --harness <tool>` plan shows `merge=0, preserve=0`; `aidlc doctor` 0 problems |
| C2 | A supported interactive agent session | documented launch command in the adapter |
| C3 | Genuine human Plan Approval via a prompt-submit / human-turn hook that mints the protected `HUMAN_TURN` authority event with an uncopyable token | `scripts/preflight.py --tool <id> --require-human-turn` passes in a real session |
| C4 | Real AI application code generation after approval | generated, buildable source in the run |
| C5 | Build + automated tests of the generated code | tool/CI test run passes |
| C6 | Independent review stage | recorded review verdict |
| C7 | Traceability from intent -> design -> code -> tests | artifacts linked in the evidence manifest's `stages[].produced_artifacts` |
| C8 | Sanitized evidence export into the shared manifest | `export_evidence.py` + `validate_evidence.py --check-artifacts` clean |

## 3. Framework-version compatibility

- The adapter declares `min_framework_version` in the tool registry entry.
- CI enforces `framework.version >= min_framework_version`
  (`scripts/check_tool_registry.py`) and the global support window
  (`scripts/check_framework_integrity.py`).

## 4. Hook / approval integration (non-negotiable)

- The adapter MUST route human approvals through the tool's interactive
  prompt-submit seam so a genuine `HUMAN_TURN` is recorded. It MUST NOT provide
  any path that fabricates `HUMAN_TURN` / `GATE_APPROVED` or bypasses the
  control. A tool that cannot record a genuine `HUMAN_TURN` cannot be CERTIFIED.

## 5. Evidence mapping (the neutral run descriptor)

The adapter produces the neutral run descriptor consumed by the tool-agnostic
`engineering-hub/evidence/exporter/export_evidence.py`:

- `tool`: `{ id, surface, adapter_version }` — `id` is the adapter's kebab-case
  identifier, which MUST exist in the tool registry.
- `framework`, `intent`, `stages`, `tests`, `artifacts`, optional
  `declared_approvals` — all tool-agnostic.
- The adapter never writes `approvals.verifiable_by_ci: true` (honesty rule).

The schema accepts ANY kebab-case `tool.id` (open contract); eligibility is
governed by the registry, not the schema.

## 6. Certification requirements

- The tool must PASS every step of `certification/certification-suite.md`
  (C1-C8 above) in a real end-to-end run.
- Results are recorded in `certification/certification-matrix.md` and the tool's
  state is set in `tool-registry.json` (CERTIFIED / FAILED / PENDING /
  UNSUPPORTED). Presence of configuration files is never certification.

## 7. Adding a new tool (repeatable process)

1. Write `onboarding/adapters/<tool>.md` implementing C1-C8 and this contract.
2. Append a `tools[]` entry to `tool-registry.json` with `state: PENDING` and
   `accept_evidence: false`.
3. Run the certification suite end-to-end; attach evidence.
4. On full PASS, set the registry `state: CERTIFIED` and `accept_evidence: true`
   via a reviewed pull request; update the matrix.
5. No change to the schema, exporter, CI logic, or shared governance is needed —
   only the registry and the new adapter.

## 8. Portability

Adapters and the registry reference tool ids, repo-relative paths, and version
strings only — no personal accounts, machine-specific paths, or credentials.
