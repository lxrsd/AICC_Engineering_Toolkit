#!/usr/bin/env python3
"""Windows onboarding + default-endpoint tests (stdlib unittest, NO network).

Covers the two P0 Windows acceptance blockers and their fixes WITHOUT touching
the network, the real aidlc runtime, or a real browser. Everything that would
reach outside the process (HTTP, subprocess, PATH lookups, webbrowser) is
monkeypatched. These are correctness tests for the Toolkit's own logic — they
do NOT constitute Windows acceptance, which must be run on a real Windows host.

Run: python3 installer/test_windows_onboarding.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import stat
import tempfile
import unittest

import install
import workbench_endpoint as we
import workbench_register as wr


def _spaced_project() -> pathlib.Path:
    """A corporate OneDrive-style path with spaces, a hyphen, and a parenthesis."""
    return (pathlib.Path(tempfile.mkdtemp())
            / "OneDrive - Company" / "Desktop" / "AICC-Test" / "expense-tracker")


@contextlib.contextmanager
def _patched(**attrs):
    """Temporarily set install.<name> = value for each kwarg."""
    saved = {k: getattr(install, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(install, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(install, k, v)


class _FakeCompleted:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def _fast_subprocess_run(cmd, *a, **k):
    """Stand in for real subprocess calls so the suite is hermetic and fast:
    the `aidlc config` step and the evidence-validation subprocess are the only
    external commands the installer runs, and both just need to look successful.
    No real runtime, no network, no slow process."""
    return _FakeCompleted(0, stdout="(stubbed) ok\n")


def _run_install(target, *, dry_run=False, api="https://wb.example", source="flag",
                 open_browser=False, allow_runtime_install=False, tool="kiro-cli"):
    buf = io.StringIO()
    # Make the runtime look present+compatible and stub the external commands so
    # the test never shells out to a real aidlc / validator (fast + portable).
    fake_sp = type("SP", (), {"run": staticmethod(_fast_subprocess_run)})
    with _patched(find_runtime_exe=lambda: "/stub/aidlc",
                  runtime_version=lambda exe=None: (2, 10, 0),
                  runtime_doctor_ok=lambda exe=None: (True, "ok"),
                  subprocess=fake_sp):
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = install.install(tool, target, assume_yes=True, non_interactive=True,
                                 allow_runtime_install=allow_runtime_install, force=False,
                                 dry_run=dry_run, workbench_api=api, api_source=source,
                                 open_browser=open_browser)
    return rc, buf.getvalue()


# ----------------------------------------------------------------------------
# FIX 2 — default endpoint + precedence
# ----------------------------------------------------------------------------
class DefaultEndpoint(unittest.TestCase):
    def test_default_is_used_when_nothing_overrides(self):
        base, source = we.resolve_api(None, env={})
        self.assertEqual(source, "default")
        self.assertEqual(base, we.DEFAULT_WORKBENCH_API)
        self.assertTrue(base.startswith("https://"))
        self.assertFalse(base.endswith("/"))

    def test_env_overrides_default(self):
        base, source = we.resolve_api(None, env={we.WORKBENCH_API_ENV: "https://env.example/"})
        self.assertEqual((base, source), ("https://env.example", "env"))

    def test_flag_overrides_env_and_default(self):
        base, source = we.resolve_api("https://flag.example///",
                                      env={we.WORKBENCH_API_ENV: "https://env.example"})
        self.assertEqual((base, source), ("https://flag.example", "flag"))

    def test_no_duplicate_api_prefix(self):
        base, _ = we.resolve_api(None, env={})
        full = base + wr.REGISTER_PATH
        # exactly one "/api/" and no "//api"
        self.assertEqual(full.count("/api/engineer-projects"), 1)
        self.assertNotIn("//api", full.replace("https://", ""))

    def test_blank_values_fall_through(self):
        base, source = we.resolve_api("   ", env={we.WORKBENCH_API_ENV: ""})
        self.assertEqual(source, "default")


# ----------------------------------------------------------------------------
# FIX 1 — runtime bootstrap (detection, consent, PATH refresh, doctor, unsupported)
# ----------------------------------------------------------------------------
class RuntimeBootstrap(unittest.TestCase):
    WIN = {"os": "windows", "arch": "amd64", "key": ("windows", "amd64"),
           "supported": True, "asset": "aidlc-windows-x64.exe",
           "is_windows": True, "in_wsl": False}
    MAC = {"os": "darwin", "arch": "arm64", "key": ("darwin", "arm64"),
           "supported": True, "asset": "aidlc-darwin-arm64",
           "is_windows": False, "in_wsl": False}
    UNSUPPORTED = {"os": "windows", "arch": "arm64", "key": ("windows", "arm64"),
                   "supported": False, "asset": None, "is_windows": True, "in_wsl": False}

    def test_missing_runtime_detected(self):
        with _patched(find_runtime_exe=lambda: None, runtime_version=lambda exe=None: None):
            ready, msg, exe = install.ensure_runtime(self.WIN, True, False, allow_install=False, dry_run=False)
        self.assertFalse(ready)
        self.assertIsNone(exe)
        self.assertIn("runtime not found", msg.lower())

    def test_existing_compatible_runtime_preserved(self):
        with _patched(find_runtime_exe=lambda: "/x/aidlc",
                      runtime_version=lambda exe=None: (2, 10, 0)):
            ready, msg, exe = install.ensure_runtime(self.WIN, True, False, allow_install=False, dry_run=False)
        self.assertTrue(ready)
        self.assertEqual(exe, "/x/aidlc")
        self.assertIn("preserved", msg)

    def test_unsupported_platform_blocked(self):
        with _patched(find_runtime_exe=lambda: None, runtime_version=lambda exe=None: None):
            ready, msg, exe = install.ensure_runtime(self.UNSUPPORTED, True, False,
                                                     allow_install=True, dry_run=False)
        self.assertFalse(ready)
        self.assertIn("no asset", msg)

    def test_below_minimum_runtime_rejected(self):
        with _patched(find_runtime_exe=lambda: "/x/aidlc",
                      runtime_version=lambda exe=None: (2, 9, 0)):
            ready, msg, _ = install.ensure_runtime(self.MAC, True, False, allow_install=True, dry_run=False)
        self.assertFalse(ready)
        self.assertIn("below the required", msg)

    def test_consent_declined_does_not_install(self):
        called = []
        with _patched(find_runtime_exe=lambda: None, runtime_version=lambda exe=None: None,
                      _run_official_installer=lambda plat: called.append(1) or (0, "x")):
            # non_interactive + assume_yes False => confirm() returns False (declined)
            ready, msg, _ = install.ensure_runtime(self.WIN, assume_yes=False, non_interactive=True,
                                                   allow_install=True, dry_run=False)
        self.assertFalse(ready)
        self.assertEqual(called, [], "installer must NOT run without consent")
        self.assertIn("declined", msg.lower())

    def test_consent_granted_runs_official_installer_then_rediscovers(self):
        state = {"installed": False}

        def fake_installer(plat):
            state["installed"] = True
            return 0, "powershell"

        def fake_find():
            return "/fresh/aidlc" if state["installed"] else None

        def fake_ver(exe=None):
            return (2, 10, 0) if state["installed"] else None

        with _patched(find_runtime_exe=fake_find, runtime_version=fake_ver,
                      _run_official_installer=fake_installer,
                      runtime_doctor_ok=lambda exe=None: (True, "ok")):
            ready, msg, exe = install.ensure_runtime(self.WIN, assume_yes=True, non_interactive=False,
                                                     allow_install=True, dry_run=False)
        self.assertTrue(ready)
        self.assertEqual(exe, "/fresh/aidlc")
        self.assertIn("installed official runtime", msg)
        self.assertIn("doctor", msg.lower())

    def test_path_not_refreshed_after_install_is_honest(self):
        # Installer runs OK but exe cannot be rediscovered (PATH not refreshed).
        with _patched(find_runtime_exe=lambda: None, runtime_version=lambda exe=None: None,
                      _run_official_installer=lambda plat: (0, "powershell"),
                      runtime_doctor_ok=lambda exe=None: (False, "n/a")):
            ready, msg, _ = install.ensure_runtime(self.WIN, True, False, allow_install=True, dry_run=False)
        self.assertFalse(ready)
        self.assertIn("new terminal", msg.lower())

    def test_doctor_failure_reported_not_claimed_ready(self):
        state = {"installed": False}
        with _patched(_run_official_installer=lambda plat: (state.update(installed=True), (0, "sh"))[1],
                      find_runtime_exe=lambda: "/x/aidlc" if state["installed"] else None,
                      runtime_version=lambda exe=None: (2, 10, 0) if state["installed"] else None,
                      runtime_doctor_ok=lambda exe=None: (False, "hook missing")):
            ready, msg, _ = install.ensure_runtime(self.MAC, True, False, allow_install=True, dry_run=False)
        self.assertFalse(ready, "doctor failure must NOT report ready")
        self.assertIn("doctor", msg.lower())

    def test_dry_run_never_installs_runtime(self):
        called = []
        with _patched(find_runtime_exe=lambda: None, runtime_version=lambda exe=None: None,
                      _run_official_installer=lambda plat: called.append(1) or (0, "x")):
            ready, msg, _ = install.ensure_runtime(self.WIN, True, False, allow_install=True, dry_run=True)
        self.assertFalse(ready)
        self.assertEqual(called, [])
        self.assertIn("DRY-RUN", msg)


# ----------------------------------------------------------------------------
# Registration success / failure / retry via the installer, + redaction
# ----------------------------------------------------------------------------
class RegistrationThroughInstaller(unittest.TestCase):
    OK = {"project_id": "SRV-1",
          "workbench_url": "https://wb.example/#/projects/SRV-1",
          "stages": [{"slug": s, "status": "pending"} for s in wr.EXPECTED_STAGES],
          "update_token": "tok-SECRET-should-not-print"}

    def _mock_request(self, responder):
        return _patched()  # placeholder; we patch wr._request directly below

    def test_successful_registration_opens_browser_and_stores_token(self):
        opened = []
        orig_req = wr._request
        wr._request = lambda m, u, b: (201, dict(self.OK))
        try:
            with _patched(webbrowser=type("W", (), {"open": staticmethod(lambda u: opened.append(u) or True)})):
                target = _spaced_project()
                rc, out = _run_install(target, open_browser=True)
            cfg = json.loads((target / ".aicc" / "config.json").read_text())
        finally:
            wr._request = orig_req
        self.assertEqual(cfg["workbench"]["status"], "REGISTERED")
        self.assertEqual(opened, ["https://wb.example/#/projects/SRV-1"])
        self.assertIn("update_token", cfg["workbench"])          # stored privately
        self.assertNotIn("tok-SECRET-should-not-print", out)      # never printed
        self.assertNotIn("tok-SECRET-should-not-print", opened[0])  # never in URL

    def test_network_failure_then_retry_reuses_same_project_id(self):
        target = _spaced_project()
        orig_req = wr._request
        try:
            # First attempt: network error -> NOT_CONNECTED, id persisted.
            wr._request = lambda m, u, b: (_ for _ in ()).throw(
                wr.RegisterError("cannot reach host", wr.STATUS_NOT_CONNECTED))
            _run_install(target)
            cfg1 = json.loads((target / ".aicc" / "config.json").read_text())
            self.assertEqual(cfg1["workbench"]["status"], "NOT_CONNECTED")
            id1 = cfg1["local_project_id"]
            # Retry: backend now up -> REGISTERED, SAME local id (no duplicate).
            ok = dict(self.OK)
            wr._request = lambda m, u, b: (201, ok)
            _run_install(target)
            cfg2 = json.loads((target / ".aicc" / "config.json").read_text())
        finally:
            wr._request = orig_req
        self.assertEqual(cfg2["workbench"]["status"], "REGISTERED")
        self.assertEqual(cfg2["local_project_id"], id1)

    def test_failed_registration_does_not_open_browser(self):
        opened = []
        orig_req = wr._request
        wr._request = lambda m, u, b: (500, {"error": "boom"})
        try:
            with _patched(webbrowser=type("W", (), {"open": staticmethod(lambda u: opened.append(u) or True)})):
                target = _spaced_project()
                _run_install(target, open_browser=True)
            cfg = json.loads((target / ".aicc" / "config.json").read_text())
        finally:
            wr._request = orig_req
        self.assertEqual(cfg["workbench"]["status"], "FAILED")
        self.assertEqual(opened, [])


# ----------------------------------------------------------------------------
# Dry-run vs real, spaced paths, no-overwrite
# ----------------------------------------------------------------------------
class DryRunAndPaths(unittest.TestCase):
    def test_dry_run_writes_nothing_and_never_reports_ready(self):
        target = _spaced_project()
        rc, out = _run_install(target, dry_run=True)
        self.assertFalse((target / ".aicc" / "config.json").exists())
        self.assertIn("DRY-RUN", out)
        self.assertNotIn("Result:            READY", out)

    def test_dry_run_does_not_register_or_open(self):
        opened = []
        orig_req = wr._request
        called = []
        wr._request = lambda m, u, b: called.append(1) or (201, {})
        try:
            with _patched(webbrowser=type("W", (), {"open": staticmethod(lambda u: opened.append(u) or True)})):
                _run_install(_spaced_project(), dry_run=True, open_browser=False)
        finally:
            wr._request = orig_req
        self.assertEqual(called, [], "dry-run must not POST registration")
        self.assertEqual(opened, [])

    def test_real_install_writes_config_at_spaced_path(self):
        orig_req = wr._request
        wr._request = lambda m, u, b: (201, {
            "project_id": "SRV-9", "workbench_url": "https://wb.example/#/projects/SRV-9",
            "stages": [{"slug": s, "status": "pending"} for s in wr.EXPECTED_STAGES]})
        try:
            target = _spaced_project()
            _run_install(target)
            cfg = json.loads((target / ".aicc" / "config.json").read_text())
        finally:
            wr._request = orig_req
        self.assertTrue(cfg["local_project_id"])
        self.assertEqual(cfg["harness"], "kiro")

    def test_existing_harness_config_not_overwritten(self):
        orig_req = wr._request
        wr._request = lambda m, u, b: (201, {
            "project_id": "SRV-7", "workbench_url": "https://wb.example/#/projects/SRV-7",
            "stages": [{"slug": s, "status": "pending"} for s in wr.EXPECTED_STAGES]})
        try:
            target = _spaced_project()
            # Pre-existing Kiro + Claude configs the engineer owns.
            (target / ".kiro" / "hooks").mkdir(parents=True)
            (target / ".kiro" / "hooks" / "my.kiro.hook").write_text("ENGINEER HOOK", encoding="utf-8")
            (target / "CLAUDE.md").parent.mkdir(parents=True, exist_ok=True)
            (target / "CLAUDE.md").write_text("ENGINEER INSTRUCTIONS", encoding="utf-8")
            (target / ".claude").mkdir(parents=True, exist_ok=True)
            (target / ".claude" / "settings.json").write_text(
                json.dumps({"hooks": {"Stop": [{"keep": "me"}]}, "custom": 1}), encoding="utf-8")
            _run_install(target)
            # The engineer's hooks + settings survive untouched.
            self.assertEqual((target / ".kiro" / "hooks" / "my.kiro.hook").read_text(), "ENGINEER HOOK")
            settings = json.loads((target / ".claude" / "settings.json").read_text())
            self.assertEqual(settings["custom"], 1)
            self.assertIn({"keep": "me"}, settings["hooks"]["Stop"])
            # CLAUDE.md: the engineer's content is PRESERVED and the AI-DLC
            # activation pointer is appended (non-destructive merge, not a clobber).
            claude = (target / "CLAUDE.md").read_text()
            self.assertIn("ENGINEER INSTRUCTIONS", claude)
            self.assertIn("AGENTS.md", claude)
        finally:
            wr._request = orig_req


# ----------------------------------------------------------------------------
# Runtime executable rediscovery (PATH-independent lookup)
# ----------------------------------------------------------------------------
class RuntimeRediscovery(unittest.TestCase):
    def test_find_runtime_falls_back_to_known_dirs(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        bindir = tmp / ".aidlc" / "bin"
        bindir.mkdir(parents=True)
        exe = bindir / ("aidlc.exe" if install.os.name == "nt" else "aidlc")
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        import shutil as _sh
        orig_which = install.shutil.which
        orig_cand = install._candidate_runtime_dirs
        try:
            install.shutil.which = lambda c: None          # not on PATH
            install._candidate_runtime_dirs = lambda: [bindir]
            found = install.find_runtime_exe()
        finally:
            install.shutil.which = orig_which
            install._candidate_runtime_dirs = orig_cand
        self.assertEqual(found, str(exe))


# ----------------------------------------------------------------------------
# Windows corporate failures: Claude off-PATH detection, OneDrive access-denied
# (read-only) sync, interrupted/resumable install, existing-hooks preservation.
# Regression for the Huron laptop crash at apply_aicc_standard()/shutil.rmtree.
# ----------------------------------------------------------------------------
class ClaudeDetection(unittest.TestCase):
    def test_claude_found_in_userprofile_local_bin_off_path(self):
        # %USERPROFILE%\.local\bin\claude.exe not on PATH must still be detected.
        home = pathlib.Path(tempfile.mkdtemp())
        binp = home / ".local" / "bin"
        binp.mkdir(parents=True)
        exe = binp / ("claude.exe" if install.os.name == "nt" else "claude")
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        with _patched(shutil=type("S", (), {"which": staticmethod(lambda n: None)}),
                      _candidate_tool_dirs=lambda: [binp]):
            found = install.find_tool_exe(("claude",))
        self.assertEqual(found, str(exe))

    def test_find_tool_exe_prefers_path(self):
        with _patched(shutil=type("S", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                      _candidate_tool_dirs=lambda: []):
            self.assertEqual(install.find_tool_exe(("claude",)), "/usr/bin/claude")

    def test_missing_tool_returns_none(self):
        with _patched(shutil=type("S", (), {"which": staticmethod(lambda n: None)}),
                      _candidate_tool_dirs=lambda: [pathlib.Path(tempfile.mkdtemp())]):
            self.assertIsNone(install.find_tool_exe(("claude",)))


class NonDestructiveApply(unittest.TestCase):
    def _toolkit_hooks_exist(self):
        return (install.TOOLKIT_ROOT / "installer" / "hooks").exists()

    def test_safe_sync_overwrites_readonly_destination(self):
        # OneDrive marks files read-only; the sync must clear it, not crash.
        src = pathlib.Path(tempfile.mkdtemp())
        (src / "sub").mkdir()
        (src / "sub" / "f.json").write_text("NEW", encoding="utf-8")
        dst = pathlib.Path(tempfile.mkdtemp()) / "hooks"
        (dst / "sub").mkdir(parents=True)
        ro = dst / "sub" / "f.json"
        ro.write_text("OLD", encoding="utf-8")
        os.chmod(ro, stat.S_IREAD)
        install._safe_sync_tree(src, dst)   # must not raise PermissionError
        self.assertEqual(ro.read_text(), "NEW")

    def test_apply_does_not_rmtree_and_preserves_engineer_files(self):
        # The exact crash scenario: an existing .aicc hooks dir with a read-only
        # file AND an engineer-owned file. apply must not rmtree it.
        proj = _spaced_project()
        hd = proj / ".aicc" / "ai-dlc" / "installer" / "hooks"
        hd.mkdir(parents=True)
        eng = hd / "engineer-notes.txt"
        eng.write_text("MINE", encoding="utf-8")
        locked = hd / "locked.hook"
        locked.write_text("x", encoding="utf-8")
        os.chmod(locked, stat.S_IREAD)
        out = install.apply_aicc_standard(proj, "claude", force=False, dry_run=False)
        # No crash; engineer file preserved (no recursive delete).
        self.assertTrue(eng.exists())
        self.assertEqual(eng.read_text(), "MINE")
        self.assertTrue(any("hook" in line for line in out))
        # cleanup read-only bit so tempdir removal doesn't warn
        os.chmod(locked, stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(proj.parent, ignore_errors=True)

    def test_apply_is_idempotent_and_resumable(self):
        # Running twice (as after an interrupted install) must converge, not fail.
        proj = _spaced_project()
        out1 = install.apply_aicc_standard(proj, "claude", force=False, dry_run=False)
        out2 = install.apply_aicc_standard(proj, "claude", force=False, dry_run=False)
        self.assertTrue(any("methodology" in l for l in out1))
        # Second pass: methodology already present (idempotent, no crash).
        self.assertTrue(any("already present" in l for l in out2))
        shutil.rmtree(proj.parent, ignore_errors=True)

    def test_access_denied_is_reported_not_crash(self):
        # If a copy genuinely cannot proceed, apply degrades to a SKIPPED note
        # instead of raising — local setup must not hard-crash.
        proj = _spaced_project()

        def boom(src, dst):
            raise PermissionError(13, "Access is denied")

        with _patched(_safe_sync_tree=boom):
            out = install.apply_aicc_standard(proj, "claude", force=False, dry_run=False)
        self.assertTrue(any("SKIPPED" in line for line in out),
                        f"expected a SKIPPED note, got: {out}")
        shutil.rmtree(proj.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
