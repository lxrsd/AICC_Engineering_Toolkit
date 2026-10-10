#!/usr/bin/env python3
"""Tests for the Toolkit evidence-submission CLI (stdlib unittest, no network).

Validates collect/validate/sanitize + the client-side contract that mirrors the
server. SYNTHETIC fixtures only. Run: python3 installer/test_submit_evidence.py
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import submit_evidence as se


def synthetic_manifest(tool="claude-code", bad_content=None, extra=None):
    m = {
        "schema_version": "1.0.0",
        "generated_at": "2026-10-10T00:00:00Z",
        "tool": {"id": tool, "surface": "Claude Code", "adapter_version": "1.0.0"},
        "framework": {"name": "AI-DLC", "version": "2.10.0", "scope": "poc"},
        "intent": {"id": "260101-synthetic", "title": "SYNTHETIC", "guard_policy": "strict"},
        "stages": [{"slug": "code-generation", "phase": "construction", "status": "completed"}],
        "tests": {"framework": "python-unittest", "total": 3, "passed": 3, "failed": 0, "results_path": "x"},
        "artifacts": [{"path": "src/app.py", "sha256": "a" * 64, "kind": "other"}],
        "approvals": {"verifiable_by_ci": False, "declared_gates": [{"stage": "code-generation", "declared_outcome": "approved"}]},
    }
    if bad_content:
        m["leak"] = bad_content
    if extra:
        m.update(extra)
    return m


def write_manifest(m: dict) -> pathlib.Path:
    p = pathlib.Path(tempfile.mkdtemp()) / "evidence-manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


class CollectValidateSanitize(unittest.TestCase):
    def test_valid_manifest_sanitized_and_kept(self):
        out = se.collect_and_validate(write_manifest(synthetic_manifest()), "myapp")
        # only metadata keys survive; no source/secret bodies
        self.assertEqual(set(out.keys()) - {"schema_version", "generated_at", "tool", "framework",
                                            "intent", "stages", "tests", "artifacts", "approvals"}, set())
        self.assertEqual(out["tool"]["id"], "claude-code")

    def test_unsupported_tool_rejected(self):
        with self.assertRaises(se.SubmitError):
            se.collect_and_validate(write_manifest(synthetic_manifest(tool="kiro-ide")), "myapp")

    def test_forbidden_content_rejected(self):
        for secret in ("AKIA" + "A"*16, "HUMAN_TURN", "sess_deadbeef12345678", "-----BEGIN RSA PRIVATE KEY-----"):
            with self.assertRaises(se.SubmitError):
                se.collect_and_validate(write_manifest(synthetic_manifest(bad_content=secret)), "myapp")

    def test_invalid_project_rejected(self):
        for bad in ("../etc", "a/b", "", "x"*100):
            with self.assertRaises(se.SubmitError):
                se.collect_and_validate(write_manifest(synthetic_manifest()), bad)

    def test_oversized_rejected(self):
        big = synthetic_manifest(extra={"padding": "x" * (se.MAX_BYTES + 10)})
        with self.assertRaises(se.SubmitError):
            se.collect_and_validate(write_manifest(big), "myapp")

    def test_forged_completion_flag_rejected_by_schema(self):
        # The strict evidence schema (additionalProperties:false) rejects a
        # forged aggregate completion field outright — the client never forwards
        # it, and the server would reject it too. Stage status is server-derived.
        m = synthetic_manifest(extra={"all_stages_green": True})
        with self.assertRaises(se.SubmitError) as e:
            se.collect_and_validate(write_manifest(m), "myapp")
        self.assertIn("schema validation", str(e.exception).lower())


class ContractAndErrors(unittest.TestCase):
    def test_submit_maps_server_rejections(self):
        orig = se._request
        try:
            se._request = lambda m, u, b: (422, {"error": "evidence rejected"})
            with self.assertRaises(se.SubmitError):
                se.submit("https://x", "p", synthetic_manifest())
            se._request = lambda m, u, b: (413, {"error": "too large"})
            with self.assertRaises(se.SubmitError) as e:
                se.submit("https://x", "p", synthetic_manifest())
            self.assertIn("413", str(e.exception))
            se._request = lambda m, u, b: (201, {"run_id": "RunId0123456789abcdef0", "url": "/#/runs/x"})
            self.assertEqual(se.submit("https://x", "p", synthetic_manifest())["run_id"], "RunId0123456789abcdef0")
        finally:
            se._request = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
