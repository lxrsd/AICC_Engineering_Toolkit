# Onboarding Adapter — Cursor (FUTURE CANDIDATE)

Track: **Future candidate — NOT officially compatible, NOT certified**
Adapter version: 0.0.1 (draft example)
Registry state: PENDING, `accept_evidence: false`

This adapter is a **worked example** of how a new AI coding environment joins
the standard through the reusable tool-adapter contract
(`../tool-adapter-specification.md`). Cursor is NOT claimed officially
compatible or certified. No Cursor evidence is accepted by CI until Cursor
completes this adapter and passes end-to-end certification, at which point its
registry entry is updated via a reviewed pull request.

## Why Cursor is here

To prove the standard is extensible: a new tool is added by writing an adapter
like this one plus a registry entry — with **no change** to the shared schema,
exporter, CI logic, or governance. This demonstrates requirement 7 (add a tool
without redesigning the methodology).

## What a real Cursor certification would require

Implement every capability in the tool-adapter specification:

| Capability | Cursor-specific mapping (to be proven) |
|------------|----------------------------------------|
| C1 isolated install | `aidlc config --harness cursor --yes`; verify `merge=0, preserve=0`, `aidlc doctor` clean |
| C2 interactive agent | documented Cursor launch that runs the AI-DLC agent |
| C3 genuine human Plan Approval | Cursor's prompt-submit integration must mint a real `HUMAN_TURN` (uncopyable token); verified by `preflight.py --tool cursor --require-human-turn` |
| C4 code generation | real buildable source after approval |
| C5 build + tests | passing |
| C6 independent review | recorded verdict |
| C7 traceability | linked artifacts in the manifest |
| C8 evidence export | `tool.id = "cursor"`; `validate_evidence.py --check-artifacts` clean |

## Current honest status

- Cursor harness is available in the AI-DLC runtime, but AICC has NOT run or
  verified an end-to-end governed lifecycle on Cursor.
- Certification matrix: all Cursor steps are NOT TESTED.
- Registry: `state: PENDING`, `accept_evidence: false` — CI rejects any Cursor
  evidence manifest until certification completes.

Do not mark Cursor CERTIFIED, and do not accept Cursor evidence, on the basis of
this draft adapter or the presence of the Cursor harness.
