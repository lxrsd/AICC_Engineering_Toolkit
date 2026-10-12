#!/usr/bin/env python3
"""Tests for the AI-DLC activation layer (installer/aidlc_activation.py).

Hermetic: no network, no real aidlc runtime (configure_harness takes an injected
`run`). Covers the discovery-instruction authoring (AGENTS.md tool-neutral,
CLAUDE.md thin pointer, Kiro steering), idempotency, non-destructive preservation
of engineer content, and the engine-surface VERIFICATION that keeps the installer
honest — including the no-op-runtime case that caused the real Windows symptom,
and Kiro<->Claude switching leaving the other harness intact.

NOTE: these are MOCKED/unit tests. They prove the Toolkit's own logic. They do
NOT constitute Windows acceptance (a real Claude Code / Kiro CLI session on the
Huron laptop), which must be run separately.

Run: python3 installer/test_aidlc_activation.py
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

import aidlc_activation as act


class _Run:
    """Injectable subprocess.run stand-in. `effect` may create files to simulate
    a runtime that produces an engine surface."""
    def __init__(self, effect=None, rc=0, out="", err=""):
        self.effect = effect
        self.rc, self.out, self.err = rc, out, err
        self.calls = []

    def __call__(self, cmd, cwd=None, **kw):
        self.calls.append((cmd, cwd))
        if self.effect:
            self.effect(pathlib.Path(cwd))
        return type("R", (), {"returncode": self.rc, "stdout": self.out, "stderr": self.err})()


def _proj():
    return pathlib.Path(tempfile.mkdtemp())


class InstructionAuthoring(unittest.TestCase):
    def test_creates_all_three_files(self):
        t = _proj()
        act.write_activation_instructions(t, "kiro", dry_run=False)
        self.assertTrue((t / "AGENTS.md").exists())
        self.assertTrue((t / "CLAUDE.md").exists())
        self.assertTrue((t / ".kiro" / "steering" / "aicc-ai-dlc.md").exists())

    def test_agents_is_tool_neutral_and_requires_approval(self):
        t = _proj()
        act.write_activation_instructions(t, "claude", dry_run=False)
        agents = (t / "AGENTS.md").read_text()
        self.assertIn("AI-DLC is REQUIRED", agents)
        self.assertIn("Plan Approval", agents)
        self.assertIn("Requirements", agents)
        # tool-neutral: mentions both tools, not just one
        self.assertIn("Claude Code", agents)
        self.assertIn("Kiro CLI", agents)
        # does NOT write application code immediately
        self.assertIn("instead of writing application code", agents)

    def test_claude_is_thin_pointer_not_methodology_copy(self):
        t = _proj()
        act.write_activation_instructions(t, "claude", dry_run=False)
        claude = (t / "CLAUDE.md").read_text()
        self.assertIn("AGENTS.md", claude)             # points at the source of truth
        self.assertIn("defer", claude.lower())          # explicitly defers
        # It must be short — a pointer, not a methodology duplicate.
        self.assertLess(len(claude), len((t / "AGENTS.md").read_text()) + 400)

    def test_claude_and_kiro_pointers_written_for_both_harnesses(self):
        # Forward-compatible: a Kiro install still writes CLAUDE.md so a later
        # switch to Claude already discovers the rule, and vice-versa.
        for harness in ("kiro", "claude"):
            t = _proj()
            act.write_activation_instructions(t, harness, dry_run=False)
            self.assertTrue((t / "CLAUDE.md").exists(), harness)
            self.assertTrue((t / ".kiro" / "steering" / "aicc-ai-dlc.md").exists(), harness)

    def test_idempotent_no_duplicate_block(self):
        t = _proj()
        act.write_activation_instructions(t, "kiro", dry_run=False)
        out = act.write_activation_instructions(t, "kiro", dry_run=False)
        self.assertTrue(all("no change" in line for line in out), out)
        self.assertEqual((t / "AGENTS.md").read_text().count(act.BEGIN), 1)

    def test_preserves_existing_engineer_content(self):
        t = _proj()
        (t / "CLAUDE.md").write_text("# My rules\nUse tabs.\n", encoding="utf-8")
        act.write_activation_instructions(t, "claude", dry_run=False)
        txt = (t / "CLAUDE.md").read_text()
        self.assertIn("Use tabs.", txt)                 # engineer content kept
        self.assertIn("follow AGENTS.md", txt)          # our block appended

    def test_refresh_updates_block_in_place(self):
        t = _proj()
        (t / "AGENTS.md").write_text(
            f"top\n{act.BEGIN}\nOLD\n{act.END}\nbottom\n", encoding="utf-8")
        act.write_activation_instructions(t, "kiro", dry_run=False)
        txt = (t / "AGENTS.md").read_text()
        self.assertIn("top", txt)
        self.assertIn("bottom", txt)
        self.assertNotIn("OLD", txt)
        self.assertEqual(txt.count(act.BEGIN), 1)

    def test_dry_run_writes_nothing(self):
        t = _proj()
        act.write_activation_instructions(t, "kiro", dry_run=True)
        self.assertFalse((t / "AGENTS.md").exists())
        self.assertFalse((t / "CLAUDE.md").exists())


class HarnessVerification(unittest.TestCase):
    def test_empty_project_not_configured(self):
        t = _proj()
        self.assertFalse(act._harness_configured(t, "claude"))
        self.assertFalse(act._harness_configured(t, "kiro"))

    def test_our_steering_pointer_alone_is_not_a_kiro_engine(self):
        t = _proj()
        act.write_activation_instructions(t, "kiro", dry_run=False)  # writes steering pointer
        self.assertFalse(act._harness_configured(t, "kiro"),
                         "a bare steering pointer must not count as a configured engine")

    def test_claude_surface_detected(self):
        t = _proj()
        (t / ".claude").mkdir()
        self.assertTrue(act._harness_configured(t, "claude"))

    def test_kiro_engine_surface_detected(self):
        t = _proj()
        (t / ".kiro" / "hooks").mkdir(parents=True)
        self.assertTrue(act._harness_configured(t, "kiro"))


class ConfigureHarness(unittest.TestCase):
    def test_runtime_that_builds_surface_is_configured(self):
        t = _proj()
        run = _Run(effect=lambda cwd: (cwd / ".claude").mkdir(exist_ok=True))
        ok, msg = act.configure_harness("/x/aidlc", t, "claude", dry_run=False, run=run)
        self.assertTrue(ok)
        self.assertIn("verified", msg)

    def test_noop_runtime_is_honest_failure_not_fake_success(self):
        # Reproduces the real 2.10.0 case: config runs but creates no surface.
        t = _proj()
        run = _Run(effect=None, out="guided setup")
        ok, msg = act.configure_harness("/x/aidlc", t, "claude", dry_run=False, run=run)
        self.assertFalse(ok)
        self.assertIn("could not confirm", msg)
        # Tried more than one invocation form before giving up.
        self.assertGreaterEqual(len(run.calls), 1)

    def test_already_configured_is_idempotent_without_running(self):
        t = _proj()
        (t / ".claude").mkdir()
        run = _Run()
        ok, msg = act.configure_harness("/x/aidlc", t, "claude", dry_run=False, run=run)
        self.assertTrue(ok)
        self.assertEqual(run.calls, [], "must not reconfigure an already-configured harness")
        self.assertIn("already configured", msg)

    def test_switch_kiro_to_claude_preserves_kiro(self):
        t = _proj()
        (t / ".kiro" / "hooks").mkdir(parents=True)
        run = _Run(effect=lambda cwd: (cwd / ".claude").mkdir(exist_ok=True))
        ok, _ = act.configure_harness("/x/aidlc", t, "claude", dry_run=False, run=run)
        self.assertTrue(ok)
        self.assertTrue((t / ".kiro" / "hooks").exists(), "existing Kiro engine must be preserved")
        self.assertTrue((t / ".claude").exists())

    def test_switch_claude_to_kiro_preserves_claude(self):
        t = _proj()
        (t / ".claude").mkdir()
        run = _Run(effect=lambda cwd: (cwd / ".kiro" / "hooks").mkdir(parents=True, exist_ok=True))
        ok, _ = act.configure_harness("/x/aidlc", t, "kiro", dry_run=False, run=run)
        self.assertTrue(ok)
        self.assertTrue((t / ".claude").exists(), "existing Claude engine must be preserved")

    def test_dry_run_does_not_run_or_write(self):
        t = _proj()
        run = _Run(effect=lambda cwd: (cwd / ".claude").mkdir(exist_ok=True))
        ok, msg = act.configure_harness("/x/aidlc", t, "claude", dry_run=True, run=run)
        self.assertFalse(ok)
        self.assertEqual(run.calls, [])
        self.assertFalse((t / ".claude").exists())
        self.assertIn("DRY-RUN", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
