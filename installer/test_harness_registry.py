#!/usr/bin/env python3
"""Tests for the central harness registry and all-seven-harness handling.

Hermetic (no network, no real runtime). Covers: registry completeness and the
upstream-grounded facts, legacy tool-id resolution, coexistence rules, detection,
engine-surface verification per harness, idempotent configuration + honest
no-op failure, non-destructive switching across harnesses, and the installer's
honest certification labeling.

HONESTY: these are MOCKED/unit tests of the Toolkit's own logic. They do NOT
constitute real-machine acceptance for ANY harness — see the support matrix in
the PR. Only claude & kiro have prior real runs (status PARTIAL); the other five
are UNTESTED on a real machine.

Run: python3 installer/test_harness_registry.py
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

import harness_registry as hreg
import aidlc_activation as act


SEVEN = ["claude", "kiro", "kiro-ide", "codex", "cursor", "opencode", "copilot"]


class RegistryShape(unittest.TestCase):
    def test_exactly_seven_official_harnesses(self):
        self.assertEqual(sorted(hreg.all_ids()), sorted(SEVEN))

    def test_each_harness_has_required_fields(self):
        for hid in SEVEN:
            h = hreg.HARNESSES[hid]
            self.assertTrue(h.display_name)
            self.assertIn(h.invoke, (hreg.INVOKE_SLASH, hreg.INVOKE_DOLLAR))
            self.assertTrue(h.engine_markers, f"{hid} needs engine markers for verification")
            self.assertTrue(h.onboarding_file, f"{hid} needs an onboarding surface")

    def test_codex_uses_dollar_invocation_and_needs_git(self):
        # Upstream: Codex invokes with $aidlc and requires a git repo.
        self.assertEqual(hreg.HARNESSES["codex"].invoke, hreg.INVOKE_DOLLAR)
        self.assertTrue(hreg.HARNESSES["codex"].requires_git_repo)

    def test_non_codex_use_slash(self):
        for hid in SEVEN:
            if hid != "codex":
                self.assertEqual(hreg.HARNESSES[hid].invoke, hreg.INVOKE_SLASH, hid)

    def test_onboarding_surfaces_match_upstream(self):
        expected = {
            "claude": ".claude/CLAUDE.md",
            "kiro": ".kiro/steering/aidlc-onboarding.md",
            "kiro-ide": ".kiro/steering/aidlc-onboarding.md",
            "codex": ".codex/onboarding.md",
            "cursor": ".cursor/rules/aidlc-onboarding.mdc",
            "opencode": ".aidlc/onboarding.md",
            "copilot": "AGENTS.md",
        }
        for hid, surf in expected.items():
            self.assertEqual(hreg.HARNESSES[hid].onboarding_file, surf, hid)

    def test_legacy_tool_ids_resolve(self):
        self.assertEqual(hreg.resolve("claude-code").id, "claude")
        self.assertEqual(hreg.resolve("kiro-cli").id, "kiro")
        self.assertEqual(hreg.resolve("codex").id, "codex")
        self.assertIsNone(hreg.resolve("not-a-harness"))

    def test_editors_flagged(self):
        self.assertTrue(hreg.HARNESSES["kiro-ide"].is_editor)
        self.assertTrue(hreg.HARNESSES["cursor"].is_editor)
        self.assertFalse(hreg.HARNESSES["claude"].is_editor)


class Coexistence(unittest.TestCase):
    def test_shared_root_block_harnesses_coexist(self):
        for a in ("kiro", "kiro-ide", "codex", "cursor", "opencode"):
            for b in ("kiro", "kiro-ide", "codex", "cursor", "opencode"):
                self.assertTrue(hreg.can_coexist(a, b), f"{a}+{b}")

    def test_copilot_is_exclusive(self):
        # Copilot's full root AGENTS.md block is exclusive upstream.
        self.assertFalse(hreg.shares_root_agents("copilot"))
        for other in ("kiro", "codex", "cursor", "opencode", "claude"):
            self.assertFalse(hreg.can_coexist("copilot", other), f"copilot+{other}")
        self.assertTrue(hreg.can_coexist("copilot", "copilot"))


class EngineVerificationPerHarness(unittest.TestCase):
    """_harness_configured must detect a real engine surface for each harness and
    NOT be fooled by the Toolkit's own activation files."""

    def _mk(self):
        return pathlib.Path(tempfile.mkdtemp())

    def test_empty_project_no_harness_configured(self):
        t = self._mk()
        for hid in SEVEN:
            self.assertFalse(act._harness_configured(t, hid), hid)

    def test_toolkit_written_files_do_not_count(self):
        # Writing AGENTS.md/CLAUDE.md/kiro steering must NOT make any harness
        # look configured — those are our activation layer, not engines.
        t = self._mk()
        act.write_activation_instructions(t, "kiro", dry_run=False)
        for hid in SEVEN:
            self.assertFalse(act._harness_configured(t, hid),
                             f"{hid} wrongly counted as configured from Toolkit files")

    def test_real_surfaces_detected(self):
        cases = {
            "claude": ".claude/CLAUDE.md",
            "kiro": ".kiro/hooks/x.hook",
            "codex": ".codex/onboarding.md",
            "cursor": ".cursor/rules/aidlc-onboarding.mdc",
            "opencode": ".aidlc/onboarding.md",
            "copilot": ".github/aidlc/x",
        }
        for hid, rel in cases.items():
            t = self._mk()
            p = t / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
            self.assertTrue(act._harness_configured(t, hid), f"{hid} surface {rel} not detected")

    def test_copilot_not_proven_by_agents_md_alone(self):
        # AGENTS.md is both Copilot's onboarding AND a Toolkit-written file, so
        # AGENTS.md alone must NOT prove Copilot's engine — require .github.
        t = self._mk()
        act.write_activation_instructions(t, "copilot", dry_run=False)  # writes AGENTS.md
        self.assertFalse(act._harness_configured(t, "copilot"))
        (t / ".github" / "aidlc").mkdir(parents=True)
        self.assertTrue(act._harness_configured(t, "copilot"))


class ConfigureAndSwitchAllHarnesses(unittest.TestCase):
    class _Run:
        def __init__(self, make_rel=None):
            self.make_rel = make_rel
            self.calls = []

        def __call__(self, cmd, cwd=None, **kw):
            self.calls.append((cmd, cwd))
            if self.make_rel:
                p = pathlib.Path(cwd) / self.make_rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    SURFACE = {
        "claude": ".claude/CLAUDE.md", "kiro": ".kiro/hooks/h", "kiro-ide": ".kiro/hooks/h",
        "codex": ".codex/onboarding.md", "cursor": ".cursor/rules/aidlc-onboarding.mdc",
        "opencode": ".aidlc/onboarding.md", "copilot": ".github/aidlc/x",
    }

    def test_configure_each_harness_verified(self):
        for hid in SEVEN:
            t = pathlib.Path(tempfile.mkdtemp())
            run = self._Run(make_rel=self.SURFACE[hid])
            ok, msg = act.configure_harness("/x/aidlc", t, hid, dry_run=False, run=run)
            self.assertTrue(ok, f"{hid}: {msg}")

    def test_noop_runtime_is_honest_failure_each(self):
        for hid in SEVEN:
            t = pathlib.Path(tempfile.mkdtemp())
            run = self._Run(make_rel=None)   # creates nothing
            ok, msg = act.configure_harness("/x/aidlc", t, hid, dry_run=False, run=run)
            self.assertFalse(ok, f"{hid} must not report configured on a no-op")
            self.assertIn("could not confirm", msg)

    def test_switch_preserves_other_harness(self):
        # Configure kiro, then switch to claude: kiro surface must remain.
        t = pathlib.Path(tempfile.mkdtemp())
        act.configure_harness("/x/aidlc", t, "kiro", dry_run=False,
                              run=self._Run(make_rel=".kiro/hooks/h"))
        self.assertTrue(act._harness_configured(t, "kiro"))
        act.configure_harness("/x/aidlc", t, "claude", dry_run=False,
                              run=self._Run(make_rel=".claude/CLAUDE.md"))
        self.assertTrue(act._harness_configured(t, "claude"))
        self.assertTrue(act._harness_configured(t, "kiro"), "switching clobbered the Kiro engine")

    def test_already_configured_is_idempotent(self):
        t = pathlib.Path(tempfile.mkdtemp())
        (t / ".codex").mkdir()
        (t / ".codex" / "onboarding.md").write_text("x", encoding="utf-8")
        run = self._Run(make_rel=".codex/onboarding.md")
        ok, msg = act.configure_harness("/x/aidlc", t, "codex", dry_run=False, run=run)
        self.assertTrue(ok)
        self.assertEqual(run.calls, [], "must not reconfigure an already-configured harness")


if __name__ == "__main__":
    unittest.main(verbosity=2)
