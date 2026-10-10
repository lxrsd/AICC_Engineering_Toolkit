# Environment Certification PR

Use this template when submitting a real-run certification result for a
supported environment. A certification PR records PASS / FAIL / NOT TESTED per
step against an ACTUAL run — never on the basis of present configuration files.

## Environment under certification

- Tool: <!-- kiro-cli | claude-code | kiro-ide | cursor -->
- Framework version: <!-- e.g. 2.10.0 -->
- Adapter version:

## Certification steps (attach evidence for each)

| # | Step | Status (PASS/FAIL/NOT TESTED) | Evidence |
|---|------|-------------------------------|----------|
| 1 | Fresh clone + isolated install |  |  |
| 2 | New independent intent |  |  |
| 3 | Requirements + design |  |  |
| 4 | Genuine human Plan Approval |  |  |
| 5 | Valid protected approval receipt |  |  |
| 6 | Working application code generation |  |  |
| 7 | Build + automated tests |  |  |
| 8 | Independent review |  |  |
| 9 | Sanitized evidence export |  |  |
| 10 | GitHub PR validation |  |  |

## Approval integrity attestation

- [ ] Plan Approval was a genuine human turn recorded via the supported
      interactive agent (verified with `scripts/preflight.py --require-human-turn`)
- [ ] No approval event was fabricated and no protected guard was bypassed
- [ ] If any step is FAIL/NOT TESTED, the overall status is NOT CERTIFIED

## Matrix update

- [ ] `docs/engineering-standard/certification/certification-matrix.md` updated
      with this environment's column and recomputed overall row
