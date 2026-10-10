#!/usr/bin/env python3
"""Positive and negative CI test fixtures for the AICC evidence contract.

Stdlib `unittest` only. Run from the repository root:

    python3 engineering-hub/evidence/exporter/test_evidence.py

Or emit machine-readable results for the evidence manifest / CI:

    python3 engineering-hub/evidence/exporter/test_evidence.py --emit-results <path>

What it proves:
  POSITIVE
    * a well-formed manifest validates
    * its artifacts verify by sha256 (--check-artifacts path)
    * the exporter reproduces a schema-valid, hash-correct manifest
  NEGATIVE
    * a schema-invalid manifest is rejected (bad semver, bad enum, missing
      required field, empty artifacts, additionalProperties)
    * a dishonest approvals block (verifiable_by_ci: true) is rejected -- the
      contract's non-fabrication rule
    * a hash-mismatched artifact is rejected
    * the sensitive-file scanner flags a leaked secret (synthesized in a
      tempdir, never committed)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent  # engineering-hub/evidence/exporter -> repo root
FIXTURES = HERE.parent / "fixtures"
SCHEMA = HERE.parent / "schema" / "evidence-manifest.schema.json"

# Path-independent resolution of the sibling check scripts and standard config
# files. In the AICC_Unified layout they live under <repo>/scripts and
# <repo>/docs/engineering-standard. In the AICC Engineering Toolkit they are
# co-located under the validators dir (HERE.parent). Prefer whichever exists so
# this test passes in both repositories with no private dependency.
def _resolve(name: str, candidates: list[pathlib.Path]) -> pathlib.Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

CHECKS = _resolve("checks", [HERE.parent, REPO_ROOT / "scripts"])
STANDARD = _resolve("standard", [HERE.parent, REPO_ROOT / "docs" / "engineering-standard"])
# The registry under STANDARD is the authoritative one in AICC_Unified or the
# sanitized public-registry.json in the Toolkit.
REGISTRY_FILE = _resolve("registry", [
    HERE.parent / "public-registry.json",
    REPO_ROOT / "docs" / "engineering-standard" / "tool-registry.json",
])

sys.path.insert(0, str(HERE))
import validate_evidence  # noqa: E402
import export_evidence  # noqa: E402


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


SCHEMA_DOC = _load(SCHEMA)


class PositiveFixtures(unittest.TestCase):
    def test_valid_manifest_passes_schema(self):
        manifest = _load(FIXTURES / "positive" / "evidence-manifest.json")
        errors = validate_evidence.validate(manifest, SCHEMA_DOC)
        self.assertEqual(errors, [], f"unexpected schema errors: {errors}")

    def test_valid_manifest_passes_honesty_rule(self):
        manifest = _load(FIXTURES / "positive" / "evidence-manifest.json")
        self.assertEqual(validate_evidence.honesty_check(manifest), [])

    def test_valid_manifest_artifacts_verify(self):
        manifest = _load(FIXTURES / "positive" / "evidence-manifest.json")
        errors = validate_evidence.check_artifacts(manifest, FIXTURES / "positive")
        self.assertEqual(errors, [], f"artifact integrity errors: {errors}")

    def test_exporter_reproduces_valid_manifest(self):
        base = FIXTURES / "positive"
        descriptor = {
            "tool": {"id": "kiro-cli", "surface": "Kiro CLI 2.x", "adapter_version": "1.0.0"},
            "framework": {"name": "AI-DLC", "version": "2.10.0", "scope": "aicc-engineering-standard"},
            "intent": {"id": "261008-multi-ide-standard", "title": "T", "guard_policy": "strict"},
            "stages": [{"slug": "code-generation", "phase": "construction", "status": "completed"}],
            "tests": {"framework": "python-unittest", "total": 3, "passed": 3, "failed": 0,
                      "results_path": "artifacts/test-results.json"},
            "artifacts": [{"path": "artifacts/sample-governance.md", "kind": "governance"}],
            "declared_approvals": [{"stage": "intent-capture", "declared_outcome": "approved"}],
        }
        manifest = export_evidence.build_manifest(descriptor, base)
        self.assertEqual(validate_evidence.validate(manifest, SCHEMA_DOC), [])
        self.assertEqual(validate_evidence.honesty_check(manifest), [])
        self.assertEqual(validate_evidence.check_artifacts(manifest, base), [])
        # exporter must encode the honesty rule
        self.assertFalse(manifest["approvals"]["verifiable_by_ci"])


class NegativeFixtures(unittest.TestCase):
    def test_schema_invalid_is_rejected(self):
        manifest = _load(FIXTURES / "negative" / "schema-invalid.json")
        errors = validate_evidence.validate(manifest, SCHEMA_DOC)
        self.assertTrue(errors, "schema-invalid fixture should produce errors")
        joined = " ".join(errors)
        self.assertIn("framework.version", joined)
        self.assertIn("guard_policy", joined)

    def test_dishonest_approvals_rejected_by_schema(self):
        manifest = _load(FIXTURES / "negative" / "dishonest-approvals.json")
        schema_errors = validate_evidence.validate(manifest, SCHEMA_DOC)
        self.assertTrue(any("verifiable_by_ci" in e or "approvals" in e for e in schema_errors),
                        f"schema should reject verifiable_by_ci: true, got {schema_errors}")

    def test_dishonest_approvals_rejected_by_honesty_rule(self):
        manifest = _load(FIXTURES / "negative" / "dishonest-approvals.json")
        self.assertTrue(validate_evidence.honesty_check(manifest),
                        "honesty_check should reject verifiable_by_ci: true")

    def test_hash_mismatch_rejected(self):
        manifest = _load(FIXTURES / "negative" / "hash-mismatch.json")
        # schema is fine; the artifact-integrity check must fail
        self.assertEqual(validate_evidence.validate(manifest, SCHEMA_DOC), [])
        errors = validate_evidence.check_artifacts(manifest, FIXTURES / "positive")
        self.assertTrue(any("sha256 mismatch" in e for e in errors),
                        f"expected a sha256 mismatch, got {errors}")

    def test_sensitive_file_scanner_flags_leaked_secret(self):
        script = CHECKS / "check_sensitive_files.py"
        patterns = STANDARD / "sensitive-file-patterns.json"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            leaked = tmp_path / "service.env"
            # Build the synthetic key from parts so THIS test file does not itself
            # contain a literal that the content scanner would flag in the repo.
            fake_key = "AKIA" + "IOSFODNN7" + "EXAMPLE"
            leaked.write_text(f"aws_secret_access_key = {fake_key}\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script), "--repo-root", str(REPO_ROOT),
                 "--patterns", str(patterns), "--extra-root", str(tmp_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1,
                             f"scanner should fail on a leaked secret; stdout={result.stdout} stderr={result.stderr}")
            self.assertIn("service.env", result.stderr)


class ToolRegistryGovernance(unittest.TestCase):
    """The contract is OPEN at the schema; eligibility is governed by the registry.

    The evidence-acceptance tests below exercise the authoritative registry's
    `accept_evidence` governance, which exists only inside AICC_Unified. The
    public AICC Engineering Toolkit ships a SANITIZED registry (no
    `accept_evidence`), so those tests are skipped there — correctly, because
    evidence-acceptance governance is not a public-toolkit responsibility."""

    @classmethod
    def _registry_has_accept_evidence(cls) -> bool:
        try:
            reg = json.loads(pathlib.Path(REGISTRY_FILE).read_text(encoding="utf-8"))
            return any("accept_evidence" in t for t in reg.get("tools", []))
        except Exception:
            return False

    def test_schema_accepts_any_kebab_tool_id(self):
        manifest = _load(FIXTURES / "negative" / "unregistered-tool.json")
        # Schema is open: an unregistered but well-formed id is schema-VALID...
        self.assertEqual(validate_evidence.validate(manifest, SCHEMA_DOC), [])

    def test_registry_rejects_unregistered_tool(self):
        if not self._registry_has_accept_evidence():
            self.skipTest("sanitized public registry: evidence-acceptance governance is AICC_Unified-only")
        script = CHECKS / "check_tool_registry.py"
        registry = REGISTRY_FILE
        result = subprocess.run(
            [sys.executable, str(script),
             "--manifest", str(FIXTURES / "negative" / "unregistered-tool.json"),
             "--registry", str(registry)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, f"registry should reject unknown tool; {result.stderr}")
        self.assertIn("not in the certification registry", result.stderr)

    def test_registry_rejects_non_evidence_accepting_tool(self):
        if not self._registry_has_accept_evidence():
            self.skipTest("sanitized public registry: evidence-acceptance governance is AICC_Unified-only")
        script = CHECKS / "check_tool_registry.py"
        registry = REGISTRY_FILE
        # hash-mismatch fixture uses kiro-ide (state FAILED, accept_evidence false)
        result = subprocess.run(
            [sys.executable, str(script),
             "--manifest", str(FIXTURES / "negative" / "hash-mismatch.json"),
             "--registry", str(registry)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, f"registry should reject non-accepting tool; {result.stderr}")
        self.assertIn("does not accept evidence", result.stderr)

    def test_registry_accepts_evidence_accepting_tool(self):
        if not self._registry_has_accept_evidence():
            self.skipTest("sanitized public registry: evidence-acceptance governance is AICC_Unified-only")
        script = CHECKS / "check_tool_registry.py"
        registry = REGISTRY_FILE
        result = subprocess.run(
            [sys.executable, str(script),
             "--manifest", str(FIXTURES / "positive" / "evidence-manifest.json"),
             "--registry", str(registry)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"registry should accept evidence-accepting tool; {result.stderr}")


def _emit_results(path: str) -> None:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(stream=open("/dev/null", "w"), verbosity=0)
    result = runner.run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    payload = {
        "framework": "python-unittest",
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "failures": [str(f[0]) for f in result.failures + result.errors],
    }
    pathlib.Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE results: {path} ({payload['passed']}/{total} passed)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--emit-results", default=None,
                        help="run tests and write a machine-readable results JSON to this path")
    args, remaining = parser.parse_known_args()
    if args.emit_results:
        _emit_results(args.emit_results)
    else:
        unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
