#!/usr/bin/env python3
"""Contract tests for the Workbench project-registration client (stdlib
unittest, NO network).

Every test monkeypatches workbench_register._request to simulate a server
response, so nothing here touches the network. The tests pin the registration
CONTRACT the backend (private AICC_Unified repo, future phase) must satisfy, and
prove the client stays HONEST when the backend is missing or misbehaves — it
never fabricates a project_id or Workbench URL.

Run: python3 installer/test_workbench_register.py
"""
from __future__ import annotations

import unittest

import workbench_register as wr


API = "https://workbench.example.test"
LOCAL_ID = "0123456789abcdef0123456789abcdef"


def _stages(status="pending", slugs=wr.EXPECTED_STAGES):
    return [{"slug": s, "status": status} for s in slugs]


def _ok_payload(project_id="SRV-abc123", url="https://workbench.example.test/#/projects/SRV-abc123"):
    return {"project_id": project_id, "workbench_url": url, "stages": _stages()}


class _Seam:
    """Context manager that swaps in a fake _request and restores it."""

    def __init__(self, responder):
        self.responder = responder
        self._orig = None
        self.calls = []

    def __enter__(self):
        self._orig = wr._request

        def fake(method, url, body):
            self.calls.append((method, url, body))
            return self.responder(method, url, body)

        wr._request = fake
        return self

    def __exit__(self, *exc):
        wr._request = self._orig
        return False


class SuccessContract(unittest.TestCase):
    def test_201_returns_project_id_url_and_six_pending_stages(self):
        with _Seam(lambda m, u, b: (201, _ok_payload())) as seam:
            result = wr.register_project(API, LOCAL_ID, "claude-code", "claude")
        self.assertEqual(result["project_id"], "SRV-abc123")
        self.assertTrue(result["workbench_url"].startswith("https://"))
        self.assertEqual([s["slug"] for s in result["stages"]], list(wr.EXPECTED_STAGES))
        self.assertTrue(all(s["status"] == "pending" for s in result["stages"]))
        # Request shape matches the contract.
        method, url, body = seam.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/engineer-projects"))
        self.assertEqual(body, {"local_project_id": LOCAL_ID, "tool": "claude-code", "harness": "claude"})

    def test_exactly_six_expected_stages(self):
        with _Seam(lambda m, u, b: (201, _ok_payload())):
            result = wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        self.assertEqual(len(result["stages"]), 6)
        self.assertEqual(tuple(s["slug"] for s in result["stages"]), wr.EXPECTED_STAGES)

    def test_idempotent_reregistration_returns_same_ids(self):
        # Same local_project_id must yield the same server ids. First call 201,
        # repeat call 200 with identical ids — both accepted as success.
        same = _ok_payload(project_id="SRV-stable-1",
                            url="https://workbench.example.test/#/projects/SRV-stable-1")
        with _Seam(lambda m, u, b: (201, same)):
            first = wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        with _Seam(lambda m, u, b: (200, same)):
            second = wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        self.assertEqual(first["project_id"], second["project_id"])
        self.assertEqual(first["workbench_url"], second["workbench_url"])


class HonestFailures(unittest.TestCase):
    def test_404_registration_not_implemented_reports_not_connected(self):
        with _Seam(lambda m, u, b: (404, {"error": "not found"})) as _:
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "claude-code", "claude")
        self.assertEqual(e.exception.status, wr.STATUS_NOT_CONNECTED)

    def test_501_not_implemented_reports_not_connected(self):
        with _Seam(lambda m, u, b: (501, {"error": "not implemented"})):
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "claude-code", "claude")
        self.assertEqual(e.exception.status, wr.STATUS_NOT_CONNECTED)

    def test_network_error_reports_not_connected(self):
        def boom(m, u, b):
            raise wr.RegisterError("cannot reach host", wr.STATUS_NOT_CONNECTED)

        with _Seam(boom):
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        self.assertEqual(e.exception.status, wr.STATUS_NOT_CONNECTED)

    def test_malformed_success_payload_is_failure_not_fabrication(self):
        # 201 but garbage body: must NOT invent ids; must raise FAILED.
        for bad in ({}, {"project_id": ""}, {"project_id": "x"},
                    {"project_id": "x", "workbench_url": "http://insecure/x", "stages": _stages()},
                    {"project_id": "x", "workbench_url": "https://ok/x"},  # no stages
                    "not-a-dict"):
            with _Seam(lambda m, u, b, _b=bad: (201, _b)):
                with self.assertRaises(wr.RegisterError) as e:
                    wr.register_project(API, LOCAL_ID, "claude-code", "claude")
                self.assertEqual(e.exception.status, wr.STATUS_FAILED)

    def test_wrong_stage_set_rejected(self):
        wrong = _ok_payload()
        wrong["stages"] = _stages(slugs=("requirements", "design", "approval", "code", "tests"))  # only 5
        with _Seam(lambda m, u, b: (201, wrong)):
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        self.assertEqual(e.exception.status, wr.STATUS_FAILED)

    def test_non_pending_stage_rejected(self):
        notpending = _ok_payload()
        notpending["stages"] = _stages(status="completed")
        with _Seam(lambda m, u, b: (201, notpending)):
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "kiro-cli", "kiro")
        self.assertEqual(e.exception.status, wr.STATUS_FAILED)

    def test_server_rejection_4xx_is_failed(self):
        with _Seam(lambda m, u, b: (400, {"error": "bad request"})):
            with self.assertRaises(wr.RegisterError) as e:
                wr.register_project(API, LOCAL_ID, "claude-code", "claude")
        self.assertEqual(e.exception.status, wr.STATUS_FAILED)

    def test_empty_api_reports_not_connected(self):
        with self.assertRaises(wr.RegisterError) as e:
            wr.register_project("", LOCAL_ID, "claude-code", "claude")
        self.assertEqual(e.exception.status, wr.STATUS_NOT_CONNECTED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
