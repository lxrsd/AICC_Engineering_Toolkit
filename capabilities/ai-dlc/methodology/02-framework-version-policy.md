# AICC Framework-Version Policy

Version: 1.0.0
Machine-readable companion: `framework-version.json`

## 1. Purpose

Pin which AWS AI-DLC runtime versions AICC supports, so that evidence produced
by any tool is comparable and reproducible, and so CI can reject work produced
on an unsupported runtime.

## 2. Supported window

The authoritative values live in `framework-version.json` and are enforced by
`scripts/check_framework_integrity.py`:

| Field | Meaning |
|-------|---------|
| `min_supported` | Lowest AI-DLC runtime version accepted (inclusive) |
| `max_supported` | Highest accepted (inclusive) |
| `pinned_recommended` | The version AICC recommends engineers install |
| `blocked` | Specific versions rejected even if inside the window |
| `required_framework_files` | Files that must be committed so evidence is reproducible from code |

The initial window pins AI-DLC **2.10.0** as both `min_supported` and
`pinned_recommended`, matching the validated Kiro CLI pilot.

## 3. How a version is declared and checked

- Each tool's onboarding adapter records the runtime version into the neutral
  run descriptor; the exporter writes it to `framework.version` in the evidence
  manifest.
- CI reads `framework.version`, parses it as semver, and fails if it is below
  `min_supported`, above `max_supported`, or in `blocked`.
- CI also fails if any `required_framework_files` entry is missing, which keeps
  the evidence reproducible from committed code rather than from a tool's
  private state.

## 4. Upgrading the window

1. Open a pull request editing `framework-version.json` and this document.
2. Re-run the certification suite for every supported environment against the
   new version and update the certification matrix.
3. Merge only after CODEOWNER review and green CI.

## 5. Portability

The policy names versions and committed file paths only. It contains no
machine-specific paths, tokens, usernames, or account identifiers, so it ports
unchanged to any corporate GitHub organization.
