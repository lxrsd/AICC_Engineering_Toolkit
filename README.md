<div align="center">

# AICC Engineering Toolkit

### Standardize AI engineering. Accelerate delivery. Scale with confidence.

**A governed AI-Driven Development Life Cycle (AI-DLC) for the official AWS Labs AI-DLC harnesses — automatic where your machine allows it, with an IT-approved manual path where corporate security restricts it.**

[![Framework](https://img.shields.io/badge/AI--DLC-v2.10.0-5B2C86)](https://awslabs.github.io/aidlc-workflows/)
[![Runtime](https://img.shields.io/badge/runtime-AWS%20Labs%20aidlc--workflows-FF9900)](https://github.com/awslabs/aidlc-workflows)
[![License](https://img.shields.io/badge/runtime%20license-MIT--0-blue)](https://github.com/awslabs/aidlc-workflows/blob/main/LICENSE)
[![Workbench](https://img.shields.io/badge/live-Workbench-5B2C86)](https://main.d1p32afqqmff9l.amplifyapp.com/)

</div>

---

## What this is

The **AICC Engineering Toolkit** lets any engineer run AICC's governed AI-DLC
engineering standard — the same lifecycle, governance, and evidence controls we
certified internally — in **their own application project**, using **Claude Code**
or **Kiro CLI**.

- **You download only this public repository.** No access to any private AICC
  platform repo is required.
- One setup command configures the AI-DLC runtime, the AICC adapter, the
  governance controls (including genuine human Plan Approval), the validators,
  and the templates.
- Your existing `CLAUDE.md`, agents, skills, hooks, and project files are
  **preserved**, never silently overwritten.

> The AI-DLC runtime itself is the open-source **AWS Labs**
> [`aidlc-workflows`](https://github.com/awslabs/aidlc-workflows) project
> (license **MIT-0**). This toolkit does **not** redistribute it — the installer
> uses AWS Labs' own official installer so you always get an authentic, signed
> build.

> **Honest expectation setting.** On a corporate-managed machine (e.g. Huron
> Windows with Netskope SSL inspection), fully automatic installation **cannot
> be guaranteed** — security policy may block script execution, downloads, or
> PATH changes. This Toolkit supports **both** an automatic path *where
> permitted* and an **IT-approved manual path** where it is not. The per-project
> AI-DLC configuration is local and does not depend on AWS.

---

## Engineer Quick Start

**Two one-time prerequisites (per machine), then per-project setup.**

1. **Install the official AI-DLC runtime once** (`aidlc`). Automatic where
   permitted, or [manual/IT-approved](#corporate-managed-windows-installation).
   Verify: `aidlc version` → `2.10.0`+.
2. **Have your AI tool** (Claude Code or Kiro CLI) installed — by you or via IT
   approval. The Toolkit does **not** install your editor/tool for you.
3. **Configure your project** (local, no AWS):
   ```bash
   # macOS / Linux
   python3 installer/install.py --target /path/to/your/project --harness claude
   # Windows PowerShell
   py installer\install.py --target "C:\path\to\your project" --harness claude
   ```
   Use `--harness kiro` for Kiro CLI. See all seven with
   `python3 installer/install.py --list-harnesses`.
4. **Start building.** Open your tool and run `/aidlc` (Codex uses `$aidlc`):
   describe the app; AI-DLC walks Requirements → Design → **human Approval** →
   Code → Tests → Evidence.

**AWS Workbench is optional and OFF by default.** Local AI-DLC needs no AWS
connectivity. To use the Workbench, add `--register-workbench` (or
`--workbench-api <url>` / `$AICC_WORKBENCH_API`).

---

<a id="corporate-managed-windows-installation"></a>
## Corporate-Managed Windows Installation

Real Huron Windows acceptance showed that managed devices can block automatic
installation. Here are the blockers we actually hit and the supported, secure
way through each. **None of these weakens security** — no TLS bypass, no
disabling OneDrive, no admin requirement, no unverified executables.

| Blocker | What you see | Supported remedy |
|---------|--------------|------------------|
| **PowerShell execution policy** | scripts refuse to run | Launch per-process: `powershell -ExecutionPolicy Bypass -File bootstrap\bootstrap.ps1 ...` (scoped to that process only; does not change machine policy). If still blocked, use the manual runtime install below and run `install.py` directly. |
| **Netskope SSL inspection / revocation** | `CERTIFICATE_VERIFY_FAILED: CA cert does not include key usage extension`, or CRL/OCSP warnings | Ask IT to re-issue the inspection CA with `keyUsage=critical,keyCertSign,cRLSign` (the proper fix). As a stopgap for *Workbench* calls only, `install.py --register-workbench --allow-legacy-tls-keyusage` relaxes **only** the strict Key-Usage check while keeping chain + hostname verification. Local setup needs no network and is unaffected. |
| **Corporate network restrictions / proxy** | downloads fail / time out | Set `HTTPS_PROXY`/`HTTP_PROXY`, or do the **manual offline runtime install** below. Per-project `install.py` needs no network. |
| **Windows PATH not refreshed** | `aidlc`/`claude` "not found" right after install | Open a **new** terminal, or let the Toolkit find it — detection also searches `%USERPROFILE%\.local\bin` and the runtime's install dirs, so `claude.exe` / `aidlc.exe` are found even off-PATH. |
| **OneDrive-managed project directory** | `PermissionError [WinError 5]` on files under `OneDrive - <org>` | Fixed: the installer never recursively deletes config dirs; it syncs files in place and clears read-only bits. Keep quotes around spaced paths. |

### Manual, IT-approved runtime install (offline-capable)

When the automatic installer is blocked, install the official runtime manually
from AWS Labs releases — **verified**, never from an unverified source:

1. On a permitted machine, download the official release asset for your OS/arch
   from `https://github.com/awslabs/aidlc-workflows/releases` plus its
   `checksums.txt` (and SLSA provenance).
2. **Verify SHA-256** before use:
   ```powershell
   # Windows PowerShell
   (Get-FileHash -Algorithm SHA256 .\aidlc-windows-x64.exe).Hash.ToLower()
   # compare against the value in checksums.txt
   ```
   ```bash
   # macOS / Linux
   shasum -a 256 ./aidlc-<os>-<arch>    # compare against checksums.txt
   ```
3. Place it in a user-scope dir on PATH (e.g. `%USERPROFILE%\.local\bin`), open a
   new terminal, and confirm `aidlc version` ≥ 2.10.0.
4. Run the per-project step: `py installer\install.py --target "<project>" --harness <id>`.

Do **not** disable TLS verification, bypass corporate controls, or run binaries
you have not checksum-verified.

---

## 🚀 Start Building with AI-DLC

New here? This is the whole journey in plain language — from downloading the
Toolkit to watching your own project Workbench open.

### What AI-DLC does

AI-DLC (AI-Driven Development Life Cycle) is a **governed** way to build software
with an AI coding tool. Instead of letting the AI write code unchecked, it walks
your idea through six clear stages — **Requirements → Design → Approval → Code →
Tests → Evidence** — and makes a **real human approve the plan** before any code
is generated. You get speed *and* control.

### Why engineers use the AICC standard

- **One consistent lifecycle** for every project and every teammate — no bespoke
  prompting rituals.
- **A human approval gate** that can't be faked, so AI never ships code nobody
  signed off on.
- **Evidence for every run** — requirements, design, tests, and artifacts are
  traceable, which is what makes a run *certifiable*.

### 1. Install the Toolkit — one command, fresh machine

Setup has **two independent parts**, in order:

1. **One-time, per machine:** the official **AWS Labs AI-DLC runtime** (`aidlc`)
   and your chosen **AI development tool** (Claude Code or Kiro CLI). These are
   installed **once** and reused by every project. On a corporate-managed device
   this step may require **IT approval or a manual install** — see
   [Corporate-Managed Windows Installation](#corporate-managed-windows-installation).
2. **Per project:** `installer/install.py` applies the AICC standard and
   configures AI-DLC for your tool in your project folder. This part is **local
   and needs no AWS connectivity**.

Where your machine allows it, the native bootstrapper automates part 1 with your
consent; otherwise you install the prerequisites manually (official releases,
verified) and run part 2 directly. One documented entry point per OS:

| Your OS | One command |
|---------|-------------|
| **Windows** (PowerShell) | `powershell -ExecutionPolicy Bypass -File bootstrap\bootstrap.ps1 -Target "C:\path\to\your project"` |
| **macOS** | `bash bootstrap/bootstrap.sh --target "/path/to/your project"` |
| **Linux** (incl. WSL2) | `bash bootstrap/bootstrap.sh --target "/path/to/your project"` |

The bootstrapper:

1. detects your OS + CPU and refuses unsupported combinations honestly;
2. detects or (**only with your explicit consent**) installs **Python 3**,
   **Git**, your chosen **AI harness** (Kiro CLI *or* Claude Code), and the
   official **AWS Labs AI-DLC runtime** — each from its official,
   publisher-verified source, in **user scope** (no admin, no hidden elevation).
   On corporate-managed machines, some of these installs may be blocked and must
   be done manually/with IT approval first;
3. then runs `installer/install.py` to apply the AICC standard and configure the
   AI-DLC harness in your project.

Already have the tools? It reuses them and never downgrades or overwrites them.
**AWS Workbench is optional and off by default** — nothing registers with AWS
unless you ask (see below). Add `--dry-run` to preview every step without
changing anything. On Windows, paths with spaces (OneDrive-backed Desktop) are
supported — keep the quotes.

**Bootstrapper options** (what the scripts actually accept): `--target`,
`--harness <id>` (`-Harness` on PowerShell), `--tool` (legacy alias),
`--no-browser`, `--ref <tag>`, `--sha256 <digest>` (`-Sha256` on PowerShell),
`--dry-run`, and (sh) `--yes`. The bootstrappers do **not** take a
`--workbench` flag; Workbench is an `install.py` option (below).

> **Prefer to drive the Python installer yourself?** If Python + your tool +
> the runtime are already installed, skip the bootstrapper and run `install.py`
> directly: `python3 installer/install.py --target /path/to/your/project
> --harness claude` (Windows: `py installer\install.py --target
> C:\path\to\your\project --harness claude`).

### 2. Choose your AI tool — and it gets *configured*, not just installed

The Toolkit supports **all seven official AWS Labs AI-DLC harnesses**. Pass
`--harness <id>` (or let the installer detect/prompt). Run
`python3 installer/install.py --list-harnesses` to see the live matrix.

| Harness id | Tool | Invoke in-tool | AICC certification | Toolkit integration |
|-----------|------|----------------|--------------------|---------------------|
| `claude` | Claude Code | `/aidlc` | ✅ Certified | PARTIAL¹ |
| `kiro` | Kiro CLI | `/aidlc` | ✅ Certified | PARTIAL¹ |
| `kiro-ide` | Kiro IDE | `/aidlc` | ⏳ (see registry) | UNTESTED² |
| `codex` | Codex CLI | **`$aidlc`** | — | UNTESTED² |
| `cursor` | Cursor | `/aidlc` | ⏳ Pending | UNTESTED² |
| `opencode` | opencode | `/aidlc` | — | UNTESTED² |
| `copilot` | GitHub Copilot | `/aidlc` | — | UNTESTED² |

¹ **PARTIAL** = logic + automated tests here and prior real runs on the tool;
current end-to-end Windows acceptance still pending.
² **UNTESTED** = registry + config/verify logic in place, but **no real-machine
acceptance yet** — the Toolkit configures them honestly and verifies the result,
but does not claim they work end-to-end until tested on a real machine.
> **Codex uses `$aidlc`, not `/aidlc`** — the Toolkit does not pretend every
> harness shares one invocation. Codex also requires the project to be a **git
> repository**.

**The one-time runtime prerequisite.** The official AWS Labs AI-DLC runtime
(`aidlc`) is installed **once per machine** (the bootstrapper/installer handles
this with your consent). Its native installer ships *every* harness runtime;
`aidlc config --harness <id>` then configures **each project** for the harness
you chose.

**It *configures* the tool, not just installs it.** For your selected harness the
Toolkit runs the official runtime to build the harness's engine surface
(`.claude/`, `.kiro/`, `.codex/`, `.cursor/`, `.opencode/`, or Copilot's
`.github/`) and **verifies it was actually created** — never claiming success on
a no-op. It also writes a shared, tool-neutral **`AGENTS.md`** activation rule
plus a thin **`CLAUDE.md`** pointer and a Kiro steering pointer, so both tools
auto-discover that a build request must start the governed workflow.

**Switching tools is supported and non-destructive.** Re-run with a different
`--harness`: the new harness is configured and the previous one's configuration
is left intact. Per upstream, `kiro`, `kiro-ide`, `codex`, `cursor`, and
`opencode` can **coexist** in one project (they share the root `AGENTS.md`
block); **GitHub Copilot's root block is exclusive**, so configure Copilot on
its own. Your existing agents, skills, hooks, settings, and instructions are
**preserved**, never overwritten.

#### Simple folder layout

```
your-project/
├── AGENTS.md                 # shared AI-DLC activation rule (all tools)
├── CLAUDE.md                 # thin pointer to AGENTS.md (Claude Code)
├── .aicc/
│   ├── config.json           # your stable project id + harness + Workbench status
│   └── ai-dlc/               # AICC methodology, validators, templates (namespaced)
├── .claude/ | .kiro/ | .codex/ | .cursor/ | .opencode/ | .github/
│                             # the official engine surface for your harness(es)
└── (your application source — untouched)
```

The Toolkit does **more than install the tool** — it *configures the official
AWS Labs AI-DLC methodology for the tool you selected* in your project:

- Runs the official runtime to build the **AI-DLC engine surface** for your
  harness (`.kiro/` for Kiro CLI, `.claude/` for Claude Code) and **verifies it
  was actually created** — it won't claim "configured" on a no-op.
- Writes a tool-neutral **`AGENTS.md`** (the AI-DLC activation instruction) plus
  a thin **`CLAUDE.md`** that points Claude at `AGENTS.md`, and a Kiro steering
  pointer, so each tool can **discover** that a build request should start the
  governed workflow.

> **Honest limit on "automatic activation."** Project instructions *guide* a
> tool; the runtime's harness hooks are what *enforce* the gates. The degree of
> automatic, no-prompt activation and approval enforcement is **verified only
> for the harnesses marked accordingly** in `--list-harnesses` (today: Claude
> Code and Kiro CLI are *partially* verified; the other five are **UNTESTED** on
> a real machine). We do **not** promise universal natural-language activation
> or approval enforcement for every harness.

**Switching tools later is supported and non-destructive.** Re-run the installer
with the other `--harness`: it configures that harness and leaves the first
one's configuration intact (`kiro`, `kiro-ide`, `codex`, `cursor`, `opencode`
can coexist; GitHub Copilot's root block is exclusive). Your project identity is
reused — no framework files to rebuild by hand.

> **What "configured" means in practice:** on a verified harness (Claude Code,
> Kiro CLI), open the project and type *"Build me an Expense Tracker web
> application."* — the tool should start the official AI-DLC process
> (**Requirements → Design → human Plan Approval → Code → Tests → Evidence**)
> rather than writing code immediately. Confirm this per harness on your machine.

### 3. (Optional) Workbench — off by default

Local AI-DLC is complete without AWS. The Workbench is **entirely optional** and
**not** part of the default setup — nothing contacts AWS unless you opt in with
`--register-workbench` (or `--workbench-api <url>` / `$AICC_WORKBENCH_API`).

When you opt in, the Toolkit gives your project a **stable local identity**,
registers it, and on success:

1. saves your personal project URL into `.aicc/config.json`,
2. opens that URL in your browser (skip with `--no-browser`), and
3. shows your **six lifecycle stages starting as _pending_**.

This is **your own project** — not our certified demo (see
[the distinction below](#two-things-you-can-open)).

> Registration is honest: on any failure (unreachable backend, corporate TLS,
> etc.) the installer reports `NOT_CONNECTED`/`FAILED`, **never** fabricates a
> project URL, and your **local setup still completes**. Re-run with
> `--register-workbench` to retry — your stable project id is reused, so no
> duplicate project is created.

### 4. Start building

Open your tool and describe the app you want to build:

```bash
claude            # Claude Code      → then: /aidlc "Build <your application>"
kiro-cli chat     # Kiro CLI         → then: /aidlc "Build <your application>"
```

**You approve the plan as a real human at the gate** — code generation is
blocked until you do. That gate is the whole point: it's how the AICC standard
guarantees a person, not an AI, authorized what gets built.

### What the six stages mean

| Stage | What it is |
|-------|-----------|
| **Requirements** | What the application must do, captured from your intent. |
| **Design** | How it will be built — architecture and approach. |
| **Approval** | The human gate: *you* approve the plan before any code is written. |
| **Code** | The AI generates the real application code. |
| **Tests** | The build runs and automated tests execute. |
| **Evidence** | Traceable artifacts (paths + hashes + results) proving the run. |

These six stages are the local AI-DLC lifecycle your tool runs — **no AWS
required**. *If* you opt into the Workbench (`--register-workbench`), the Toolkit
also installs a sync hook that pushes validated progress so the Workbench's
stages update automatically, with no manual evidence upload or AICC login; a
stage turns complete only when the backend validates genuine evidence (the human
approval gate must be real, and failed tests never show complete). Without the
Workbench, the same lifecycle still runs locally in your tool.

<a id="two-things-you-can-open"></a>
### Two things you can open — don't confuse them

| | What it is | For |
|---|-----------|-----|
| **▶ View Certified Demonstration** | Our *existing* certified Kiro CLI and Claude Code runs on the live Workbench. Proof that the standard works. | Seeing AICC's own completed proof. |
| **🛠 Start Building** | *Your* brand-new AI-DLC project, with its own identity and its own six pending stages. | Building your application. |

The installer only ever opens **your** project. It will **never** open our
certification showcase as if it were your run.

---

## Quick Start (one command per OS)

**Step 1 — get the toolkit**

```bash
git clone https://github.com/lxrsd/AICC_Engineering_Toolkit.git
cd AICC_Engineering_Toolkit
```

**Step 2 — run the one-command setup, pointed at your project**

<table>
<tr><th>OS</th><th>Setup command</th></tr>
<tr>
<td><b>macOS</b></td>
<td>

```bash
python3 installer/install.py --target /path/to/your/project
```

</td>
</tr>
<tr>
<td><b>Linux / WSL2</b></td>
<td>

```bash
python3 installer/install.py --target /path/to/your/project
```

</td>
</tr>
<tr>
<td><b>Windows (PowerShell)</b></td>
<td>

```powershell
py installer\install.py --target C:\path\to\your\project
```

</td>
</tr>
</table>

The installer detects your OS/CPU, detects (or asks for) **Claude Code** or
**Kiro CLI**, checks for the AI-DLC runtime, applies the AICC standard, wires the
approval controls, validates, and prints **READY** or **BLOCKED** with exactly
what to fix.

If the AI-DLC runtime is not yet installed, the installer tells you the official
AWS Labs command and (with your confirmation, `--allow-runtime-install` on
macOS/Linux) can run it for you:

```bash
# macOS / Linux / WSL2
curl -fsSL https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.sh | sh
```
```powershell
# Windows PowerShell
irm https://github.com/awslabs/aidlc-workflows/releases/latest/download/install.ps1 | iex
```

Non-interactive automation: add `--non-interactive --yes --tool claude-code|kiro-cli`.
In headless / CI environments also add `--no-browser` so no browser window is
launched. To register your project with a Workbench, pass
`--workbench-api <base-url>` (or set `$AICC_WORKBENCH_API`); when it's omitted
the installer completes local setup and reports the Workbench as
`NOT_CONNECTED` rather than inventing a URL.

---

## Supported tools

| Tool | Status | Setup (handled by the installer) | Launch |
|------|--------|----------------------------------|--------|
| **Claude Code** | ✅ Certified (Owner-Authorized Pilot) | `aidlc config --harness claude` | `claude` → `/aidlc` |
| **Kiro CLI** | ✅ Certified (Owner-Authorized Pilot) | `aidlc config --harness kiro` | `kiro-cli chat` → `/aidlc` |
| Cursor | ⏳ Pending (placeholder only) | — | — |
| Kiro IDE | ❌ Not certified on this toolkit | — | — |

Certification status is read from the sanitized public registry
(`capabilities/ai-dlc/validators/public-registry.json`), a projection of AICC's
authoritative registry. Only certified tools are offered as approved options.

### Your existing agents & skills are preserved

The installer namespaces the AICC standard under `<your-project>/.aicc/ai-dlc/`
and runs the runtime's own `aidlc config`, which reports a plan and does not
clobber your files. Existing `CLAUDE.md`, `.claude/agents`, `.claude/skills`,
`.claude/hooks`, `.kiro/`, and `AGENTS.md` are detected and preserved; conflicts
are reported, never silently overwritten.

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
<!-- Text fallback: Requirements -> Design -> Human Plan Approval gate (code
generation is blocked until a real human approves) -> Code Generation ->
Build & Tests -> Evidence + Validation -> Finalized run. -->

Each stage produces traceable artifacts. The lifecycle maps to the six Workbench
tabs: **Requirements, Design, Approval, Code, Tests, Evidence.**

## Genuine human approval & governance

AI code generation **cannot begin** until a real human approves the plan. The
runtime records a protected `HUMAN_TURN` authority event only when a real prompt
flows through your tool's interactive prompt-submit hook, using an uncopyable
token. Driving the engine from outside that interactive seam records no
`HUMAN_TURN`, and the engine refuses the approval — **by design**.

- Approvals are **never fabricated** and gates are **never bypassed**.
- Verify your environment enforces it:
  `python3 .aicc/ai-dlc/validators/preflight.py --tool <tool> --require-human-turn`
- CI/validators check committed evidence only; they never claim to verify
  protected approval receipts they cannot see.

---

## Start building

1. Open your tool's interactive AI-DLC agent (`claude`, or `kiro-cli chat`).
2. Run `/aidlc "Build <your application>"`.
3. Answer each stage; **approve at the gate as a real human**.
4. The tool generates real application code, runs build + tests, performs an
   independent review, and produces evidence.

## Build, test & validate evidence

```bash
# Validate the toolkit's own evidence contract + independence:
python3 capabilities/ai-dlc/validators/exporter/test_evidence.py
python3 installer/test_independence.py

# After a governed run, export + validate your sanitized evidence:
python3 .aicc/ai-dlc/validators/exporter/export_evidence.py --descriptor <run>.json --repo-root . --out evidence-manifest.json
python3 .aicc/ai-dlc/validators/exporter/validate_evidence.py evidence-manifest.json --repo-root . --check-artifacts
python3 .aicc/ai-dlc/validators/check_sensitive_files.py --repo-root .
```

## Workbench

### ▶ View Certified Demonstration (AICC's existing proof)

A live demonstration of our **previously certified** Kiro CLI and Claude Code
runs on the AICC AI-DLC Workbench. This is AICC's own proof that the governed
lifecycle works end-to-end — **it is not your project**:

**→ https://main.d1p32afqqmff9l.amplifyapp.com/**

### 🛠 Start Building (your own project)

The Workbench is **optional**. If you opt in (`--register-workbench`), the
Toolkit registers **your** project and opens **your** personal Workbench URL — a
fresh run with its own identity and its own six pending stages, separate from
the certified demonstration above. Without it, AI-DLC runs fully locally in your
tool with no AWS connectivity.

---

## Prerequisites

One-time, per machine (reused by every project):

- **The official AI-DLC runtime** (`aidlc`) — **mandatory**. Install it once
  (automatic where permitted, or
  [manual/IT-approved](#corporate-managed-windows-installation)); verify with
  `aidlc version` → `2.10.0`+.
- **Your AI tool** — Claude Code (`claude`) or Kiro CLI (`kiro-cli`), installed
  by you or via **IT approval**. The Toolkit does not install your tool for you.
- **Python 3.9+** (for the installer and validators).
- Supported OS/CPU per the AWS Labs runtime: macOS (arm64/x64), Linux
  (arm64/x64, incl. musl), Windows (x64). On Windows use PowerShell for the
  runtime installer, or WSL2 with the Linux command.

**Not required:** AWS connectivity or an AWS Workbench account — the Workbench is
optional and off by default.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `aidlc: command not found` after install | Open a new terminal (PATH update), or follow the installer's PATH instruction. |
| Installer prints **BLOCKED: runtime not found** | Run the official AWS Labs install command for your OS (above), then re-run the installer. |
| Installer prints **BLOCKED: `<tool>` not found** | Install Claude Code or Kiro CLI from its vendor, then re-run. |
| Approvals are refused | That is the control working. Launch the **interactive** agent (`claude` / `kiro-cli chat`) so a real `HUMAN_TURN` is recorded; don't drive the engine from a non-interactive shell. |
| Windows: `install.sh` fails in PowerShell | Use the PowerShell command (`irm … install.ps1 | iex`) or WSL2 with the Linux command. |
| `aidlc doctor` reports problems | Follow its suggested fixes; re-run the installer with `--force` to refresh the AICC standard. |
| PowerShell: *"running scripts is disabled"* | Launch per-process: `powershell -ExecutionPolicy Bypass -File bootstrap\bootstrap.ps1 ...` (scoped; no machine-policy change). If still blocked, do the manual runtime install and run `install.py` directly. |
| `CERTIFICATE_VERIFY_FAILED: CA cert does not include key usage extension` (Netskope) | A corporate SSL-inspection CA lacks a required extension. Proper fix: IT re-issues the CA with `keyUsage=critical,keyCertSign,cRLSign`. Stopgap for Workbench calls only: `--register-workbench --allow-legacy-tls-keyusage` (keeps chain + hostname checks). Local setup is unaffected. |
| `PermissionError [WinError 5]` under `OneDrive - <org>` | Fixed — the installer no longer recursively deletes config dirs and clears read-only bits. Keep quotes around spaced paths; re-run. |
| `claude`/`aidlc` "not found" right after install | PATH not refreshed: open a new terminal. Detection also searches `%USERPROFILE%\.local\bin`, so a fresh install is usually found anyway. |

See [Corporate-Managed Windows Installation](#corporate-managed-windows-installation) for the full blocker-by-blocker guide.

## Scope & honesty

- **Certified** = proved the complete governed lifecycle end-to-end in a real run
  (owner-authorized pilot, subject to corporate review on migration). Pending,
  failed, and future states are shown honestly.
- **Cursor** and **Factory AI** are placeholders — not implemented, not certified.
- This toolkit configures and references the AWS Labs runtime; it does not fork
  or redistribute it.

## License

This toolkit's AICC-authored materials are maintained by AICC. The AI-DLC runtime
is AWS Labs `aidlc-workflows` under **MIT-0**; see its repository for terms.
