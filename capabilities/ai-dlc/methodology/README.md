# AICC AI-DLC Onboarding (shared, tool-independent)

This directory onboards an AICC engineer to the AWS AI-DLC lifecycle in a
**supported, isolated** way. The shared steps below are identical for every
tool; the tool-specific details live in a **separate adapter** per environment
under `adapters/`.

Supported environments and their certification track:

| Environment | Adapter | Track |
|-------------|---------|-------|
| Kiro CLI | `adapters/kiro-cli.md` | Officially validated |
| Claude Code | `adapters/claude-code.md` | Next validation (certification pilot) |
| Kiro IDE | `adapters/kiro-ide.md` | Separate track — blocked by an approval-integration defect |
| Cursor | (future) | Future scope |

## The lifecycle every engineer must be able to run

A supported environment must let any engineer, from a fresh clone, complete the
full AWS AI-DLC lifecycle — not just produce documents:

1. Fresh clone + isolated install (no inherited sessions/receipts/paths/state)
2. A NEW, independent AI-DLC intent
3. Requirements and design stages
4. **Genuine, recorded human Plan Approval** (not fabricated)
5. A valid protected approval receipt in the engine ledger
6. Working AI-generated application source code
7. Successful build and automated tests
8. Independent review
9. Sanitized evidence export (the tool-independent contract)
10. A GitHub pull request that passes the standard's CI

## Shared steps (same for all tools)

1. **Clone fresh.** Clone the approved repository into a new directory. Do not
   copy another engineer's working tree, `aidlc/.aidlc-sessions/`,
   `aidlc/.aidlc-clone-id`, cursors, or `.aidlc-engine/` state.
2. **Install the harness for your tool** using the official command in your
   tool's adapter. A correct install creates a clean workspace with no copied
   state (`create=N, merge=0, preserve=0`).
3. **Run preflight diagnostics:** `python3 scripts/preflight.py --tool <id>`.
   It fails clearly if the AI-DLC agent, the human-prompt hook, the framework
   version, or the approval machinery are missing or misconfigured.
4. **Launch the interactive AI-DLC agent** per your adapter. This is required
   so the human-prompt hook fires and genuine Plan Approval can be recorded.
   Driving `aidlc engine` from a non-interactive outer agent does NOT record a
   `HUMAN_TURN` and will correctly block Construction at the gate.
5. **Run the lifecycle**: `/aidlc "<what you want to build>"`, answer the
   stages, approve at each gate as a real human, let the framework generate
   code, test, review, and complete.
6. **Export sanitized evidence** and open a pull request.

## Why the interactive agent matters (approval integrity)

The AI-DLC human-presence control records a `HUMAN_TURN` authority event only
when a real human prompt flows through the tool's prompt-submit hook, using an
uncopyable internal token. This is what makes a Plan Approval genuine and
un-fabricable. If you drive the engine from outside that interactive seam, the
ledger records no `HUMAN_TURN`, and the engine refuses to record approvals —
by design. Never bypass this; launch the interactive agent instead.

## Portability

Nothing here hardcodes a path, token, username, or account. Every command
resolves the repository and user context from the engineer's own clone and
environment, so it ports unchanged to Huron's corporate GitHub.
