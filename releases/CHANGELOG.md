# AICC Engineering Toolkit — release notes

## v0.1.0 (unreleased — pre-publication candidate)

First extracted distribution of the AICC AI-DLC engineering standard as a
standalone, public, engineer-facing toolkit.

- Methodology: AI-DLC overview, governance policy, framework-version policy,
  evidence contract, branch-protection guidance, universal onboarding, tool-adapter spec.
- Adapters: Kiro CLI (certified), Claude Code (certified), Cursor (pending/future).
- Validators: evidence exporter + validator, schema, positive/negative fixtures,
  preflight, framework-integrity / required-artifacts / sensitive-file / tool-registry checks,
  and the sanitized public certification registry.
- Templates: PR template, CODEOWNERS sample, branch-protection sample.
- Installer: `installer/install.py` (lists capabilities, installs AICC adapter
  config for a certified tool, drives the authorized `aidlc` runtime if present,
  runs post-install validation; non-destructive and idempotent).
- Factory AI: future placeholder only.

The AI-DLC runtime is NOT redistributed here; it is obtained from its authorized
`aidlc` source. This candidate is not labeled production-ready until an actual
installation test completes against a real engineer environment with the runtime present.
