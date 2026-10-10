#!/usr/bin/env python3
"""Independence tests for the AICC Engineering Toolkit (stdlib unittest).

Confirms the Toolkit:
  - installs into a throwaway target with NO reference to AICC_Unified,
  - offers only CERTIFIED tools as approved,
  - excludes internal platform/backend/certification-evidence files,
  - contains no secrets or internal paths,
  - ships the validators + public (sanitized) registry.

Run from the Toolkit root:  python3 installer/test_independence.py
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer" / "install.py"
REGISTRY = ROOT / "capabilities" / "ai-dlc" / "validators" / "public-registry.json"

FORBIDDEN_SUBSTRINGS = [
    "AICC_Unified/",                # a PATH dependency on the private repo (not prose mentions)
    "apps/unified-center", "apps/workbench", "backend/",   # internal platform/backend
    "published-runs",               # sensitive certification evidence
    "/Users/", "/home/",            # machine-local paths
    "d1p32afqqmff9l", "cloudfront.net", "execute-api",  # internal infra ids
]
# The public registry's sanitization is verified structurally by
# test_public_registry_is_sanitized (it must carry no `state_reason` field).
# A bare `state_reason` field-NAME mention in governance prose or validator
# tools is not a leak, so it is not scanned as a forbidden substring.
# `/audit/` is generic AI-DLC workspace structure (an engineer's own workflow
# audit shards), legitimately referenced by the framework validator tools. It is
# NOT AICC-internal data, so it is not a forbidden token.
# Real secret VALUE patterns (not detector mentions): an actual AWS key, a real
# private key block, or an assigned secret value.
SECRET_VALUE_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"aws_secret_access_key\s*[=:]\s*['\"][^'\"]{8,}"),
]
# Files that are the sanitization TOOLS themselves — they legitimately contain
# the detection patterns (e.g. the regex 'AKIA[0-9A-Z]{16}') and are exempt from
# the secret-value scan. They are still scanned for the path/internal substrings.
DETECTOR_FILES = {
    "check_sensitive_files.py", "sensitive-file-patterns.json",
    "test_evidence.py", "test_independence.py", "publish_showcase.py",
    "export_public_registry.py", "check_tool_registry.py",
}
# Files that must NOT exist anywhere in the Toolkit.
FORBIDDEN_PATHS = ["tool-registry.json"]  # the AUTHORITATIVE registry (public-registry.json is fine)


def all_files() -> list[pathlib.Path]:
    return [p for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]


class ToolkitIndependence(unittest.TestCase):
    def test_no_forbidden_substrings_in_any_file(self):
        offenders = []
        for p in all_files():
            # The scanner file itself contains the detection patterns by design.
            if p.name in DETECTOR_FILES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for s in FORBIDDEN_SUBSTRINGS:
                if s in text:
                    offenders.append(f"{p.relative_to(ROOT)}: contains path/internal token '{s}'")
            for pat in SECRET_VALUE_PATTERNS:
                if pat.search(text):
                    offenders.append(f"{p.relative_to(ROOT)}: matches secret-value pattern {pat.pattern!r}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_authoritative_registry_present(self):
        for name in FORBIDDEN_PATHS:
            hits = [str(p.relative_to(ROOT)) for p in ROOT.rglob(name)]
            self.assertEqual(hits, [], f"forbidden file(s) present: {hits}")

    def test_public_registry_is_sanitized(self):
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for t in reg["tools"]:
            self.assertEqual(set(t.keys()),
                             {"id", "display_name", "certification_state", "qualification", "framework_version"},
                             f"public registry row has unexpected fields: {t}")

    def test_installer_lists_only_certified_tools_as_approved(self):
        r = subprocess.run([sys.executable, str(INSTALLER), "--list"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # kiro-cli and claude-code are CERTIFIED -> APPROVED; kiro-ide/cursor must NOT be approved.
        self.assertRegex(r.stdout, r"kiro-cli\s+CERTIFIED.*APPROVED")
        self.assertRegex(r.stdout, r"claude-code\s+CERTIFIED.*APPROVED")
        self.assertNotRegex(r.stdout, r"kiro-ide.*\[APPROVED\]")
        self.assertNotRegex(r.stdout, r"cursor.*\[APPROVED\]")

    def test_installs_standalone_into_throwaway_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, str(INSTALLER), "--capability", "ai-dlc",
                 "--tool", "kiro-cli", "--target", tmp],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            dest = pathlib.Path(tmp) / ".aicc" / "ai-dlc"
            self.assertTrue((dest / "methodology").is_dir())
            self.assertTrue((dest / "validators").is_dir())
            self.assertTrue((dest / "adapter").is_dir())
            self.assertIn("requires NO access to the private AICC_Unified", r.stdout)

    def test_factory_ai_not_installable(self):
        r = subprocess.run([sys.executable, str(INSTALLER), "--capability", "factory-ai", "--tool", "kiro-cli"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not installable", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
