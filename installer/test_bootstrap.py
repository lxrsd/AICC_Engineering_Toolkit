#!/usr/bin/env python3
"""Tests for the native bootstrappers (bootstrap.sh / bootstrap.ps1).

Two layers, both hermetic (no network, no real installs):

  * FUNCTIONAL (bootstrap.sh): run the POSIX bootstrapper in --dry-run against a
    OneDrive-style path with spaces and assert it detects prerequisites, uses
    the in-checkout Toolkit, and hands off to install.py --dry-run writing
    nothing. Skipped automatically if bash is unavailable.

  * CONTRACT (both scripts): static assertions that each bootstrapper honors the
    non-negotiable requirements — consent gating, user-scope (no hidden
    elevation), integrity verification, honest unsupported-arch handling, no
    secret/token echoing, and the correct install.py handoff flags. These run
    everywhere, including CI without PowerShell, so the Windows script's
    contract is still enforced on every platform even though it can only be
    EXECUTED on Windows (stated plainly, not faked).

Run: python3 installer/test_bootstrap.py
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOTSTRAP_DIR = ROOT / "bootstrap"
SH = BOOTSTRAP_DIR / "bootstrap.sh"
PS1 = BOOTSTRAP_DIR / "bootstrap.ps1"


class BootstrapFilesExist(unittest.TestCase):
    def test_both_entry_points_present(self):
        self.assertTrue(SH.is_file(), "bootstrap/bootstrap.sh must exist")
        self.assertTrue(PS1.is_file(), "bootstrap/bootstrap.ps1 must exist")

    def test_sh_is_executable(self):
        if os.name == "nt":
            self.skipTest("executable bit not meaningful on Windows")
        self.assertTrue(os.access(SH, os.X_OK), "bootstrap.sh should be executable")


@unittest.skipUnless(shutil.which("bash"), "bash not available")
class ShellBootstrapFunctional(unittest.TestCase):
    def _run(self, target, *extra):
        return subprocess.run(
            ["bash", str(SH), "--target", str(target), "--tool", "kiro-cli",
             "--yes", "--no-browser", "--dry-run", *extra],
            capture_output=True, text=True, timeout=120)

    def test_syntax_valid(self):
        r = subprocess.run(["bash", "-n", str(SH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_dry_run_spaced_path_hands_off_and_writes_nothing(self):
        base = pathlib.Path(tempfile.mkdtemp())
        target = base / "OneDrive - Company" / "Desktop" / "AICC-Test" / "expense-tracker"
        r = self._run(target)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        # Prerequisite detection ran.
        self.assertIn("Detected:", out)
        self.assertIn("Python:", out)
        # Used this checkout (no download) and handed off to install.py --dry-run.
        self.assertIn("Using the Toolkit from this checkout", out)
        self.assertIn("Handing off to the AICC installer", out)
        self.assertIn("DRY-RUN (no changes made", out)
        # Nothing was written at the spaced path.
        self.assertFalse((target / ".aicc" / "config.json").exists())
        shutil.rmtree(base, ignore_errors=True)

    def test_help_exits_clean(self):
        r = subprocess.run(["bash", str(SH), "--help"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn("bootstrap.sh", r.stdout)

    def test_unknown_arg_is_rejected(self):
        r = subprocess.run(["bash", str(SH), "--frobnicate"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)


class ShellBootstrapContract(unittest.TestCase):
    def setUp(self):
        self.text = SH.read_text(encoding="utf-8")

    def test_consent_gated_installs(self):
        # A confirm() gate exists and prerequisite installs route through it.
        self.assertIn("confirm()", self.text)
        self.assertIn("Install Python 3 now", self.text)

    def test_no_sudo_for_user_scope_python_on_macos(self):
        # macOS Python path uses Homebrew / official installer, never sudo.
        self.assertIn("install_python_macos", self.text)
        macos_block = self.text.split("install_python_macos()")[1].split("install_python_linux()")[0]
        self.assertNotIn("sudo", macos_block)

    def test_integrity_verification_present(self):
        self.assertIn("SHA-256", self.text)
        self.assertIn("--sha256", self.text)
        self.assertIn("mismatch", self.text)

    def test_tls_pinned_download(self):
        self.assertIn("--proto '=https'", self.text)
        self.assertIn("archive/refs/tags/", self.text)  # pinned tag, not a branch

    def test_unsupported_arch_is_honest(self):
        self.assertIn("unsupported CPU architecture", self.text)
        self.assertIn("unsupported OS", self.text)

    def test_proxy_diagnostics(self):
        self.assertIn("PROXY", self.text.upper())

    def test_handoff_flags(self):
        for flag in ("--target", "--allow-runtime-install", "--tool", "--no-browser", "--dry-run"):
            self.assertIn(flag, self.text)

    def test_no_secret_echo(self):
        # The only mentions of the token must be in comments stating it is NEVER
        # printed — never in an echo/print statement. (The bootstrapper doesn't
        # handle the token at all; install.py keeps it in the project config.)
        for ln in self.text.splitlines():
            stripped = ln.strip()
            if "update_token" in ln:
                self.assertTrue(stripped.startswith("#"),
                                f"update_token referenced outside a comment: {ln!r}")
            # No output statement may carry a token-like value.
            if stripped.startswith(("say", "info", "warn", "echo", "printf")):
                self.assertNotIn("update_token", ln)
                self.assertNotIn("token", ln.lower())


class PowerShellBootstrapContract(unittest.TestCase):
    """Static contract for the Windows bootstrapper. It can only be EXECUTED on
    Windows; these assertions enforce its requirements on every platform so the
    contract is checked in CI, without pretending it was run on Windows."""

    def setUp(self):
        self.text = PS1.read_text(encoding="utf-8")

    def test_consent_gated_installs(self):
        self.assertIn("Confirm-Action", self.text)
        self.assertIn("Install Python 3 now", self.text)

    def test_user_scope_no_hidden_elevation(self):
        # winget installs are user scope; no RunAs/elevation.
        self.assertIn("--scope user", self.text)
        self.assertIn("InstallAllUsers=0", self.text)  # python.org per-user
        self.assertNotIn("Start-Process -Verb RunAs", self.text)

    def test_winget_has_official_fallback(self):
        # Does not rely on winget alone (CTO: broken winget sources).
        self.assertIn("Install-PythonViaWinget", self.text)
        self.assertIn("Install-PythonViaOrg", self.text)
        self.assertIn("python.org", self.text)

    def test_integrity_verification_present(self):
        self.assertIn("Get-FileHash", self.text)
        self.assertIn("-Algorithm SHA256", self.text)
        self.assertIn("mismatch", self.text)

    def test_pinned_tls_download(self):
        self.assertIn("archive/refs/tags/", self.text)
        self.assertIn("Tls12", self.text)

    def test_path_refresh_after_install(self):
        # Rediscovers Python when the live-process PATH is not refreshed.
        self.assertIn('GetEnvironmentVariable("Path"', self.text)
        self.assertIn("NEW PowerShell window", self.text)

    def test_unsupported_arch_is_honest(self):
        self.assertIn("unsupported CPU architecture", self.text)

    def test_proxy_diagnostics(self):
        self.assertIn("HTTPS_PROXY", self.text)

    def test_handoff_flags(self):
        for flag in ("--target", "--allow-runtime-install", "--tool", "--no-browser", "--dry-run"):
            self.assertIn(flag, self.text)

    def test_spaced_path_safe_handoff(self):
        # Native call operator with an array (no string concatenation of args).
        self.assertIn("$pyArgs", self.text)
        self.assertIn("@pyArgs", self.text)

    def test_no_secret_echo(self):
        # Strip the PowerShell block comment <# ... #> (the SYNOPSIS), then the
        # token must not appear in executable code at all, and no output
        # statement may carry a token value.
        import re
        code = re.sub(r"<#.*?#>", "", self.text, flags=re.DOTALL)
        for ln in code.splitlines():
            stripped = ln.strip()
            if "update_token" in ln:
                self.assertTrue(stripped.startswith("#"),
                                f"update_token referenced outside a comment: {ln!r}")
            if stripped.startswith(("Say", "Info", "Warn", "Write-", "Read-Host")):
                self.assertNotIn("token", ln.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
