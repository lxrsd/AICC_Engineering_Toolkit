<div align="center">

# AICC Engineering Toolkit

### Standardize AI engineering. Accelerate delivery. Scale with confidence.

**A governed AI-Driven Development Life Cycle (AI-DLC) for the official AWS Labs AI-DLC harnesses — configure any project in one command.**

[![Framework](https://img.shields.io/badge/AI--DLC-v2.10.0-5B2C86)](https://awslabs.github.io/aidlc-workflows/)
[![Runtime](https://img.shields.io/badge/runtime-AWS%20Labs%20aidlc--workflows-FF9900)](https://github.com/awslabs/aidlc-workflows)
[![License](https://img.shields.io/badge/runtime%20license-MIT--0-blue)](https://github.com/awslabs/aidlc-workflows/blob/main/LICENSE)

</div>

---

## What this is

The **AICC Engineering Toolkit** lets any engineer run AICC's governed AI-DLC
engineering standard in **their own application project**, using an official
AWS Labs AI-DLC coding tool (harness). It walks every build through six stages —
**Requirements → Design → Human Approval → Code → Tests → Evidence** — so a real
person approves the plan before any code is generated.

- You download only this **public** repository. No access to any private AICC
  repo and **no AWS account** is required.
- The AI-DLC runtime is the open-source **AWS Labs**
  [`aidlc-workflows`](https://github.com/awslabs/aidlc-workflows) project
  (**MIT-0**). This Toolkit configures and references it — it never forks or
  redistributes it.
- Your existing application files and tool configuration are **preserved**,
  never overwritten.

Setup is two things, kept separate:

1. **One-time per computer** — install the AI-DLC runtime and your AI tool.
2. **Per project** — run the Toolkit installer, pointed at your project folder.

You do **not** reinstall the runtime for each project.

---

## Step 1 — One-time computer setup

Do this **once per machine**. It is reused by every project.

### 1a. Install the official AI-DLC runtime (`aidlc`)

| OS | Install command |
|----|-----------------|
| **macOS** | `curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh \| sh` |
| **Windows** (PowerShell) | `irm https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1 \| iex` |

These run the **official AWS Labs installer**, which verifies its own
checksums/signatures. Then confirm:

```bash
aidlc version      # expect 2.10.0 or newer
```

> **If corporate security blocks the installer** (PowerShell execution policy,
> an SSL-inspection proxy such as Netskope, or blocked downloads), use the
> **approved manual/offline install** instead — never bypass a security control:
>
> 1. On a permitted machine, download the official release asset for your
>    OS/arch from <https://github.com/awslabs/aidlc-workflows/releases> **and**
>    its `checksums.txt`.
> 2. **Verify the SHA-256** before use:
>    `shasum -a 256 ./aidlc-<os>-<arch>` (macOS) or
>    `(Get-FileHash -Algorithm SHA256 .\aidlc-windows-x64.exe).Hash` (Windows) —
>    compare against `checksums.txt`.
> 3. Place the verified binary in a user-scope folder on your `PATH`
>    (e.g. `%USERPROFILE%\.local\bin` on Windows, `~/.local/bin` on macOS),
>    open a **new** terminal, and confirm `aidlc version`.
>
> Do not disable TLS verification, change machine-wide policy, or run binaries
> you have not checksum-verified. Ask IT to approve the runtime where required.

### 1b. Install your AI development tool

Install (or get IT approval for) **one** supported tool — the Toolkit does not
install your editor/CLI for you. See the full support table in
[Supported harnesses](#supported-harnesses). The two AICC-certified tools are:

- **Claude Code** (`claude`)
- **Kiro CLI** (`kiro-cli`)

---

## Step 2 — Download the AICC Engineering Toolkit

Clone it, or download the ZIP and extract it:

```bash
git clone https://github.com/lxrsd/AICC_Engineering_Toolkit.git
# — or — download the ZIP from the GitHub "Code" button and extract it, e.g.:
#   Windows: right-click the .zip → Extract All
#   macOS:   double-click the .zip
cd AICC_Engineering_Toolkit
```

Keep this folder **alongside** your application projects — it configures them;
it is not where your app lives.

---

## Step 3 — Configure your application project

Point the installer's `--target` at a **new or existing** project folder and
choose your tool with `--harness`:

```bash
# macOS / Linux
python3 installer/install.py --target /path/to/your/project --harness claude

# Windows (PowerShell) — keep quotes if the path has spaces (e.g. OneDrive)
py installer\install.py --target "C:\path\to\your project" --harness claude
```

Use `--harness kiro` for Kiro CLI, or any id from
[Supported harnesses](#supported-harnesses). See them live with:

```bash
python3 installer/install.py --list-harnesses
```

The installer, in your project, **non-destructively**:

- applies the AICC AI-DLC standard, validators and templates under `.aicc/ai-dlc/`;
- configures the official AI-DLC engine surface for your harness (e.g.
  `.claude/`, `.kiro/`) using the runtime, and **verifies** it was created;
- writes a tool-neutral **`AGENTS.md`** activation instruction plus a thin
  **`CLAUDE.md`** pointer and a Kiro steering pointer, so your tool discovers
  that a build request should start the governed workflow.

Your existing application files, hooks, settings and instructions are preserved
(the Toolkit merges, never clobbers). Re-running is safe and idempotent, and you
can switch tools later by re-running with a different `--harness` — the previous
harness's configuration is left intact.

Useful flags (all real): `--dry-run` (preview, change nothing), `--force`
(refresh the AICC standard), `--non-interactive` + `--yes` (automation),
`--list` / `--list-harnesses`. **No AWS account or AWS connectivity is required.**

---

## Step 4 — Start building

Open your **project folder** in your AI tool and ask it to build something, e.g.
*"Build me an Expense Tracker web application."* Start the governed workflow with
your harness's invocation:

| Harness | Start command |
|---------|---------------|
| Claude Code, Kiro CLI, Kiro IDE, Cursor, opencode, GitHub Copilot | `/aidlc` |
| **Codex CLI** | `$aidlc` |

AI-DLC then guides you through the six stages:

**Requirements → Design → Human Approval → Code → Tests → Evidence.**

At the **Human Approval** gate, you approve the plan as a real person — on the
certified harnesses, code generation is blocked until you do.

> **Honest limit.** Project instructions *guide* a tool; the runtime's hooks are
> what *enforce* the gates. Fully automatic, no-prompt activation and approval
> enforcement are proven only on harnesses that passed real end-to-end
> acceptance. Today **Claude Code and Kiro CLI are AICC-certified** (integration
> partially verified); the other five are upstream-supported but **UNTESTED** by
> AICC on a real machine. Confirm behavior on your own machine for those.

---

## Step 5 — Save your project

Your source code and AI-DLC artifacts are **yours** and live in **your** project
folder. Commit them to **your own** GitHub repository — nothing here depends on
AWS.

Before you commit, take a minute to make sure nothing sensitive goes in. Run
these in your project folder, in order:

```bash
cd /path/to/your/project

# 1. Make sure a .gitignore exists and lists secrets/local files to skip.
#    Open .gitignore and review it (e.g. .env, credentials, local config).
cat .gitignore

# 2. Run the validators — they flag sensitive files and check your evidence.
python3 .aicc/ai-dlc/validators/check_sensitive_files.py --repo-root .
python3 .aicc/ai-dlc/validators/exporter/validate_evidence.py evidence-manifest.json --repo-root . --check-artifacts

# 3. See what git would include.
git status

# 4. Stage your files (prefer naming them over "git add .").
git add <files you want to commit>

# 5. Review exactly what you staged — read it before committing.
git diff --cached

# 6. Commit and push to YOUR repository.
git init                     # only if the project isn't a repo yet
git commit -m "AI-DLC: requirements, design, code, tests, evidence"
git branch -M main
git remote add origin https://github.com/<you>/<your-project>.git
git push -u origin main
```

If a validator reports a problem, fix it before staging — don't commit until
`git diff --cached` shows only what you intend to publish.

---

## Supported harnesses

All seven official AWS Labs AI-DLC harnesses can be configured. Status is honest:
**AICC cert** is AICC's certification; **Toolkit** is how far the Toolkit's own
integration is *proven*.

| Harness id | Tool | Invoke | AICC certification | Toolkit integration |
|-----------|------|--------|--------------------|---------------------|
| `claude` | Claude Code | `/aidlc` | ✅ Certified | PARTIAL¹ |
| `kiro` | Kiro CLI | `/aidlc` | ✅ Certified | PARTIAL¹ |
| `kiro-ide` | Kiro IDE | `/aidlc` | see registry | UNTESTED² |
| `codex` | Codex CLI | **`$aidlc`** | — | UNTESTED² |
| `cursor` | Cursor | `/aidlc` | Pending | UNTESTED² |
| `opencode` | opencode | `/aidlc` | — | UNTESTED² |
| `copilot` | GitHub Copilot | `/aidlc` | — | UNTESTED² |

¹ **PARTIAL** — logic plus automated tests and prior real runs on the tool;
current end-to-end acceptance on a managed machine still pending.
² **UNTESTED** — the Toolkit configures them honestly and verifies the engine
surface, but there has been **no real-machine acceptance**; nothing is claimed
VERIFIED until that happens.

Codex invokes with `$aidlc` (not `/aidlc`) and requires the project to be a git
repository. `kiro`, `kiro-ide`, `codex`, `cursor`, and `opencode` can coexist in
one project; **GitHub Copilot's root block is exclusive** — configure it alone.

---

## The AI-DLC lifecycle

```mermaid
flowchart LR
    R[Requirements] --> D[Design]
    D --> A{Human Plan Approval}
    A -- approved --> C[Code Generation]
    A -- blocked --> A
    C --> T[Build & Tests]
    T --> E[Evidence + Validation]
    E --> F([Finalized run])
```

Each stage produces traceable artifacts. AI code generation **cannot begin**
until a real human approves the plan: the runtime records a protected
`HUMAN_TURN` only when a real prompt flows through your tool's interactive
prompt-submit hook. Approvals are never fabricated and gates are never bypassed.

Verify your environment enforces it:

```bash
python3 .aicc/ai-dlc/validators/preflight.py --tool <harness> --require-human-turn
```

---

## No AWS required

Local AI-DLC is complete without AWS. **No AWS account or AWS connectivity is
required** at any step — the full lifecycle runs locally in your tool.

---

## Prerequisites

One-time, per machine (reused by every project):

- **The official AI-DLC runtime** (`aidlc`) — mandatory; `aidlc version` ≥ 2.10.0.
- **Your AI tool** — installed by you or via IT approval.
- **Python 3.9+** — for the installer and validators.
- Supported OS/CPU per the AWS Labs runtime: macOS (arm64/x64), Linux
  (arm64/x64), Windows (x64). On Windows use PowerShell, or WSL2 with the Linux
  installation instructions.

**Not required:** an AWS account or AWS connectivity.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `aidlc: command not found` after install | Open a new terminal (PATH refresh), or re-run; detection also searches `%USERPROFILE%\.local\bin`. |
| Installer prints **BLOCKED: runtime not found** | Complete Step 1 (install the runtime), then re-run. |
| Tool reported **NOT found** | Install your AI tool from its vendor (or get IT approval), then re-run. |
| PowerShell: *"running scripts is disabled"* | For the runtime one-liner, follow IT's approved method, or use the manual/offline install in Step 1. |
| `CERTIFICATE_VERIFY_FAILED: CA cert does not include key usage extension` (Netskope) | Ask IT to re-issue the inspection CA with `keyUsage=critical,keyCertSign,cRLSign`. Local setup needs no network and is unaffected. |
| `PermissionError [WinError 5]` under `OneDrive - <org>` | The installer no longer recursively deletes config dirs and clears read-only bits — keep quotes around spaced paths and re-run. |
| Approvals are refused | That is the control working. Launch the **interactive** agent so a real `HUMAN_TURN` is recorded; don't drive the engine from a non-interactive shell. |

---

## Scope & honesty

- **Certified** = AICC proved the complete governed lifecycle end-to-end in a
  real run (owner-authorized pilot). Only **Claude Code** and **Kiro CLI** are
  certified; other harnesses are upstream-supported and shown honestly as
  UNTESTED by AICC until real-machine acceptance.
- This Toolkit configures and references the AWS Labs runtime; it does not fork
  or redistribute it, and requires no access to any private AICC repository.

## License

This Toolkit's AICC-authored materials are maintained by AICC. The AI-DLC runtime
is AWS Labs `aidlc-workflows` under **MIT-0**; see its repository for terms.
