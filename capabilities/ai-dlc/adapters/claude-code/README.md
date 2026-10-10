# Onboarding Adapter — Claude Code

Track: **Certification pilot (PENDING)**
Adapter version: 1.1.0

This adapter maps Claude Code's native AI-DLC install into the shared, tool-
independent lifecycle in `../README.md`. It is separate from shared governance
by design; nothing shared depends on Claude-specific internals.

An environment is compliant only when the approval hooks are **proven to
execute** in the active workflow. Configuration files being present is never
enough.

## 1. Supported execution surfaces

AI-DLC governance depends on Claude Code **project hooks** (the human-turn
hook and the plan-approval guard) running on every prompt and tool call, with a
real person typing in an interactive session. Only Claude Code surfaces can do
this. A "Claude" chat window is not Claude Code.

| Surface | How to recognise it | AICC status |
|---------|---------------------|-------------|
| Claude desktop app → **Code** tab (Claude Code) | `CLAUDE_CODE_ENTRYPOINT=claude-desktop` | **VERIFIED** — genuine `HUMAN_TURN` and `PLAN_APPROVAL_RECORDED` recorded in a real governed run (Run B, 2026-10-08) |
| Claude Code CLI (`claude` in a terminal) | `CLAUDE_CODE_ENTRYPOINT=cli` | **UNVERIFIED** — same hook engine; not yet proven in an AICC governed run |
| Claude Code VS Code / JetBrains extensions | `claude-vscode` / `claude-jetbrains` | **UNVERIFIED** |
| Claude Code on the web / cloud sessions | `remote` | **UNSUPPORTED** — not verified to run project hooks with the local `aidlc` runtime |
| Headless / print mode (`claude -p`), Agent SDK | `sdk-*` | **UNSUPPORTED** — no interactive human turn, so approvals can never be genuine |
| Claude desktop or web **Chat** (not the Code tab) | no `CLAUDECODE=1` in its environment | **UNSUPPORTED** — no project hooks, no shell |

`scripts/preflight.py --mode session` detects the surface from the session's own
environment and fails on an unsupported one. Use a VERIFIED surface for
certification work; an UNVERIFIED surface passes preflight but its first
governed run must be verified before it is listed as VERIFIED here.

## 2. Prerequisites

- A Claude Code surface from the table above (for the desktop app: install the
  Claude desktop app and open the **Code** tab; for the CLI: `claude --version`).
- The `aidlc` runtime on `PATH`, inside the window in
  `../../framework-version.json` (`aidlc version` → runtime 2.10.0).
- Python 3 (for the preflight and evidence scripts).
- No enterprise or Huron-specific access is required. If your organization
  manages Claude Code settings, a managed policy that sets `disableAllHooks` or
  `allowManagedHooksOnly` blocks the AI-DLC hooks; preflight fails in that case
  and you need the policy owner to allow the project hooks.

## 3. Install (fresh clone, no copied state)

```bash
git clone <approved repository URL>
cd <clone>
aidlc config --harness claude --yes   # skip if the clone already carries .claude/ from the standard
aidlc doctor
python3 scripts/preflight.py --tool claude-code --mode setup
```

Expect a clean `create=N, merge=0, preserve=0` install plan, `aidlc doctor` with
0 problems, and preflight `PASS`. Setup mode fails if any mandatory hook is
missing from `.claude/settings.json`, if any settings layer sets
`disableAllHooks`, if `AIDLC_UNATTENDED` is set, if the runtime is outside the
version window, or if the tree carries another engineer's protected state
(`aidlc/.aidlc-sessions/`, `aidlc/.aidlc-clone-id`).

Save the preflight output; it is evidence for certification step 1.

> Installing the Claude harness is an explicit, approved action. Do not install
> it into a repository without the repository owner's approval.

Mandatory hooks (checked by preflight):

| Event | Hook | Purpose |
|-------|------|---------|
| `UserPromptSubmit` | `record-human-turn` | Records a `HUMAN_TURN` for each real prompt |
| `PostToolUse` (`AskUserQuestion`) | `record-human-turn` | Records a `HUMAN_TURN` when a person answers a structured question |
| `PreToolUse` (writes, shell, agents) | `plan-approval-guard` | Refuses code generation before Plan Approval |
| `PreToolUse` | `state-transition-guard`, `review-freeze` | Protect workflow state and reviewed artifacts |
| `SessionStart` | `session-start` | Binds the session and resumes the workflow |

## 4. Approve the hooks and fully restart (required)

Claude Code does not run project hooks until you trust them.

1. Open the project in your Claude Code surface. When Claude Code asks you to
   review or trust the project's hooks, approve them. In the CLI you can also
   review them with `/hooks`.
2. **Fully restart** the surface so the approved hooks load: quit the desktop
   app completely (Cmd+Q on macOS) and reopen it, or exit and relaunch `claude`.
   Starting a new conversation or `/clear` is not enough.
3. Approve the commands the framework uses when prompted (the shipped
   `.claude/settings.json` pre-approves the framework's own commands; your
   project's build and test commands prompt once).

## 5. Prove the hooks execute (session check)

In the Claude Code session, send one real prompt (for example `/aidlc` with a
description of your work), then ask the agent to run, or run yourself from the
session's shell tool:

```bash
python3 scripts/preflight.py --tool claude-code --mode session
```

PASS requires: a supported surface detected from the session environment, an
active workflow identified from `aidlc/spaces/<space>/intents/active-intent`,
and a `HUMAN_TURN` from **this session** in **that workflow's** ledger. Turns
recorded in any other workflow do not count. A FAIL here means the hooks are
not executing — repeat step 4.

## 6. Run the lifecycle

In the interactive session, start the AI-DLC skill and describe the build;
answer each stage and approve at each gate as a real human. After genuine Plan
Approval the framework generates application code, runs build + tests,
performs an independent review, and completes the lifecycle.

> Do not drive `aidlc engine ...` from a non-interactive outer process to run
> the governed lifecycle, and do not try to invoke hooks or edit
> `aidlc/.aidlc-sessions/`. The plan-approval guard refuses tool calls that try
> to invoke a hook or touch protected session records, and the engine refuses
> approvals without a recorded human turn, by design.

Before governed Construction, and again at the end for certification:

```bash
python3 scripts/preflight.py --tool claude-code --require-human-turn
```

PASS requires every `PLAN_APPROVAL_RECORDED` in the active workflow to be
preceded by a `HUMAN_TURN` from the same session, after its approval prompt.

## 7. Evidence export

This adapter emits a neutral run descriptor with `tool.id = "claude-code"`,
`tool.surface = "Claude Code"`, `tool.adapter_version`, then calls the
tool-independent `engineering-hub/evidence/exporter/export_evidence.py`.
Commit the export under `engineering-hub/evidence/exports/<run>/`; CI validates
every committed `evidence-manifest.json` there (schema, artifact hashes,
framework window, tool registry, and `SHA256SUMS`).

## 8. Certification

Claude Code is certified only when every row of its certification suite
(`../../certification/`) is PASS against a real run, and a reviewer approves the
certification pull request — never because `.claude/` exists. Record the result
in `../../certification/certification-matrix.md`.
