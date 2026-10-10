# AICC Branch-Protection Settings (documented)

Version: 1.0.0
Scope: the default branch (`main`) of any repository adopting this standard.

These are the **documented, portable** branch-protection settings AICC requires.
They are authored as settings to apply, not applied by this repository's code —
applying them is an administrative action a repository owner performs in the
GitHub organization (Settings -> Branches, or via the GitHub API / `gh`).
This document changes no live protection by itself.

## 1. Required settings on `main`

| Setting | Value | Why |
|---------|-------|-----|
| Require a pull request before merging | Enabled | No direct pushes to `main` |
| Required approving reviews | >= 1 | Human review bar |
| Dismiss stale approvals on new commits | Enabled | Re-review changed work |
| Require review from Code Owners | Enabled | `.github/CODEOWNERS` must sign off |
| Require status checks to pass | Enabled | Gate on CI |
| Required status check | `engineering-standard-validation` | The standard's CI must be green |
| Require branches up to date before merging | Enabled | No stale-base merges |
| Require conversation resolution | Enabled | No unresolved review threads |
| Require linear history | Enabled | Matches trunk-based squash-merge policy |
| Include administrators | Enabled | Owners are not exempt |
| Allow force pushes | Disabled | Protect history |
| Allow deletions | Disabled | Protect the branch |

## 2. How an owner applies them (example, no identifiers hardcoded)

Using the GitHub CLI against whatever repository the clone points at (the
`OWNER/REPO` is read from the clone's own remote, never hardcoded):

```bash
# Resolve the current repo from the clone's remote; nothing is hardcoded.
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

gh api -X PUT "repos/$REPO/branches/main/protection" \
  --input docs/engineering-standard/branch-protection.sample.json
```

A ready-to-edit request body is provided at
`branch-protection.sample.json` in this directory. It contains only settings
and the literal context name `engineering-standard-validation` — no tokens,
usernames, or account identifiers.

## 3. Boundaries honored by this standard

This standard, and the standardization pull request that introduces it, do
**not** change repository-wide or organization-wide protections automatically.
Enabling protection is an explicit owner decision. The standard only documents
the required settings and supplies a portable request body.

## 4. Portability

All examples resolve the target repository dynamically from the clone's own
remote. There are no hardcoded owners, repository names, tokens, or paths, so
this ports unchanged to Huron's corporate GitHub.
