# Onboarding Adapter — Kiro CLI

Track: **Officially validated**
Adapter version: 1.0.0

This adapter maps Kiro CLI's native AI-DLC install into the shared, tool-
independent lifecycle in `../README.md`. It is intentionally separate from the
shared governance so no shared rule depends on Kiro-specific hooks.

## Prerequisites

- `kiro-cli` on PATH (`kiro-cli --version`).
- The `aidlc` runtime on PATH (`aidlc version` should report runtime 2.10.0,
  matching the framework-version policy).

## Install (isolated, no copied state)

From a fresh clone of the approved repository:

```bash
aidlc config --harness kiro --yes
aidlc doctor
```

A correct result is a clean `create=N, update=0, merge=0, preserve=0,
remove=0, conflict=0` plan and `aidlc doctor` reporting 0 problems. This creates
`.kiro/`, `AGENTS.md`, `aidlc/`, and the AI-DLC `.gitignore` split. It copies no
sessions, receipts, cursors, or `.aidlc-engine/` state.

## Launch the interactive agent (required for genuine Plan Approval)

The install ships `.kiro/settings/cli.json` with `chat.defaultAgent: "aidlc"`,
so launching plain interactive chat uses the AI-DLC agent and wires the
prompt-submit hook `aidlc-record-human-turn.kiro.hook`:

```bash
kiro-cli chat
```

If you prefer not to rely on the workspace default:

```bash
kiro-cli chat --agent aidlc
```

Inside that session the prompt-submit hook records a `HUMAN_TURN` on every real
prompt, which is what makes Plan Approval genuine.

> IMPORTANT: Do NOT drive `aidlc engine ...` from the default (non-AI-DLC) Kiro
> CLI agent via a shell/tool call to run the governed lifecycle. That path does
> not pass your prompts through the prompt-submit hook, so no `HUMAN_TURN` is
> recorded and the engine correctly refuses to register approvals. Use
> `kiro-cli chat` (AI-DLC agent) for the governed run.

## Run the lifecycle

In the interactive AI-DLC session:

```
/aidlc "Build <your application>"
```

Answer each stage; approve at each gate as a real human. After genuine Plan
Approval the framework generates code, runs build + tests, performs an
independent review, and completes the lifecycle.

## Neutral run descriptor (for the exporter)

When exporting evidence, this adapter produces a neutral run descriptor with
`tool.id = "kiro-cli"`, `tool.surface = "Kiro CLI 2.x"`, and
`tool.adapter_version = "1.0.0"`, then calls the tool-independent
`engineering-hub/evidence/exporter/export_evidence.py`.

## Preflight

```bash
python3 scripts/preflight.py --tool kiro-cli
```

Fails clearly if `aidlc`/`kiro-cli` are missing, the version is out of policy,
the `aidlc` agent or the prompt-submit hook is not configured, or prior
protected state is present in what should be a fresh clone.
