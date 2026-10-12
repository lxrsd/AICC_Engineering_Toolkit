#!/usr/bin/env python3
"""Tests for the automatic Workbench lifecycle sync client (stdlib, NO network).

Monkeypatches workbench_sync._post so nothing touches the network. All fixtures
are explicitly SYNTHETIC; none represents a real engineer lifecycle. Proves:
registration is required, evidence is required, forbidden content is refused,
the update_token (not the project_id) is what is sent, and honest statuses are
returned for an undeployed/unreachable backend.

Run: python3 installer/test_workbench_sync.py
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import workbench_sync as ws


SYNTH_MANIFEST = {
    "schema_version": "1.0.0",
    "generated_at": "2026-01-01T00:00:00Z",
    "tool": {"id": "kiro-cli", "surface": "SYNTHETIC", "adapter_version": "1.0.0"},
    "framework": {"name": "AI-DLC", "version": "2.10.0", "scope": "synthetic"},
    "intent": {"id": "260101-synthetic-fixture", "title": "SYNTHETIC fixture", "guard_policy": "strict"},
    "stages": [{"slug": "requirements-analysis", "phase": "inception", "status": "completed"}],
    "tests": {"framework": "pytest", "total": 3, "passed": 3, "failed": 0, "results_path": "test-results.json"},
    "artifacts": [{"path": "a.md", "sha256": "a" * 64, "kind": "requirements"}],
    "approvals": {"verifiable_by_ci": False, "declared_gates": []},
}


class _Project:
    """A temp project dir with .aicc/config.json and an evidence manifest."""

    def __init__(self, registered=True, with_evidence=True, manifest=None):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        cfg = {"local_project_id": "synthetic00000000000000000000001", "tool": "kiro-cli", "harness": "kiro"}
        if registered:
            cfg["workbench"] = {
                "status": "REGISTERED", "api": "https://workbench.example.test",
                "project_id": "SynthProjectId01234567", "update_token": "synth-update-token-abc",
            }
        (self.dir / ".aicc").mkdir(parents=True, exist_ok=True)
        (self.dir / ".aicc" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        if with_evidence:
            ev = self.dir / ".aicc" / "evidence"
            ev.mkdir(parents=True, exist_ok=True)
            (ev / "evidence-manifest.json").write_text(json.dumps(manifest or SYNTH_MANIFEST), encoding="utf-8")


class _Seam:
    def __init__(self, responder):
        self.responder = responder
        self._orig = None
        self.calls = []

    def __enter__(self):
        self._orig = ws._post

        def fake(url, body):
            self.calls.append((url, body))
            return self.responder(url, body)

        ws._post = fake
        return self

    def __exit__(self, *exc):
        ws._post = self._orig
        return False


class SyncClient(unittest.TestCase):
    def test_no_registration_is_reported(self):
        p = _Project(registered=False)
        r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.NO_REGISTRATION)

    def test_no_evidence_is_reported(self):
        p = _Project(with_evidence=False)
        r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.NO_EVIDENCE)

    def test_successful_sync_sends_update_token_not_project_id(self):
        p = _Project()
        derived = [{"slug": s, "status": "pending", "reason": "x"} for s in
                   ("requirements", "design", "approval", "code", "tests", "evidence")]
        with _Seam(lambda u, b: (200, {"project_id": "SynthProjectId01234567", "stages": derived})) as seam:
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.SYNCED)
        url, body = seam.calls[0]
        self.assertTrue(url.endswith("/api/engineer-projects/SynthProjectId01234567/updates"))
        self.assertEqual(body["update_token"], "synth-update-token-abc")
        # The project_id (view capability) must NOT be used as the auth token.
        self.assertNotEqual(body["update_token"], "SynthProjectId01234567")
        # No client "completed/green" claim is sent — only the manifest.
        self.assertIn("manifest", body)
        self.assertNotIn("stages_override", body)

    def test_undeployed_backend_reports_not_connected(self):
        p = _Project()
        with _Seam(lambda u, b: (404, {"error": "not found"})):
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.NOT_CONNECTED)

    def test_unreachable_backend_reports_not_connected(self):
        p = _Project()
        with _Seam(lambda u, b: (0, {})):
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.NOT_CONNECTED)

    def test_server_rejection_is_failed(self):
        p = _Project()
        with _Seam(lambda u, b: (403, {"error": "invalid update capability"})):
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.FAILED)

    def test_forbidden_content_refused_before_send(self):
        bad = dict(SYNTH_MANIFEST)
        # Build a synthetic AWS-key-SHAPED string at runtime so this test file
        # itself contains no literal secret-shaped token (keeps the toolkit's
        # own sensitive-substring scanner clean).
        bad["leak"] = "AK" + "IA" + "A" * 16   # matches the FORBIDDEN key shape
        p = _Project(manifest=bad)
        with _Seam(lambda u, b: (200, {"stages": []})) as seam:
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.FAILED)
        self.assertEqual(seam.calls, [])   # nothing was ever sent

    def test_unsupported_tool_refused(self):
        bad = json.loads(json.dumps(SYNTH_MANIFEST))
        bad["tool"]["id"] = "cursor"
        p = _Project(manifest=bad)
        with _Seam(lambda u, b: (200, {"stages": []})) as seam:
            r = ws.sync(p.dir)
        self.assertEqual(r.status, ws.FAILED)
        self.assertEqual(seam.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
