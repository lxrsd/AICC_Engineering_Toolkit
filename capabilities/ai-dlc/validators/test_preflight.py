#!/usr/bin/env python3
"""Regression tests for scripts/preflight.py governance checks.

Stdlib-only (unittest). Every ledger here is a synthetic fixture written to a
temporary directory; none of it is, or is presented as, real approval evidence.

Run:  python3 scripts/test_preflight.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preflight as pf  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]


def ev(event, ts, **fields):
    lines = [f"## {event}", f"**Timestamp**: {ts}", f"**Event**: {event}"]
    lines += [f"**{k}**: {v}" for k, v in fields.items()]
    return "\n".join(lines) + "\n\n---\n"


def fake_aidlc(version="aidlc 2.10.0 (runtime 2.10.0)", doctor="0 problems, 0 warnings."):
    class R:  # minimal CompletedProcess stand-in
        def __init__(self, out):
            self.stdout, self.stderr = out, ""
    return lambda args, cwd: R(version if args[0] == "version" else doctor)


GOOD_SETTINGS = {"hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "aidlc engine hook record-human-turn"}]}],
    "PostToolUse": [{"matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": "aidlc engine hook record-human-turn"}]}],
    "PreToolUse": [
        {"matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash|Task|Agent", "hooks": [{"type": "command", "command": "aidlc engine hook plan-approval-guard"}]},
        {"matcher": "Read|Edit|Write|Bash", "hooks": [{"type": "command", "command": "aidlc engine hook state-transition-guard"},
                                                     {"type": "command", "command": "aidlc engine hook review-freeze"}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "aidlc engine hook session-start"}]}],
}}


class Workspace:
    """Build a minimal synthetic AI-DLC workspace in a temp dir."""

    def __init__(self, tmp):
        self.root = pathlib.Path(tmp)
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "CLAUDE.md").write_text("# test\n")
        self.settings(GOOD_SETTINGS)
        pol = self.root / "docs" / "engineering-standard"
        pol.mkdir(parents=True)
        (pol / "framework-version.json").write_text(json.dumps(
            {"min_supported": "2.10.0", "max_supported": "2.99.99", "blocked": []}))
        self.intents = self.root / "aidlc" / "spaces" / "default" / "intents"
        self.intents.mkdir(parents=True)

    def settings(self, d, name="settings.json"):
        (self.root / ".claude" / name).write_text(json.dumps(d))

    def intent(self, name, ledger, shard="host-clone.md"):
        a = self.intents / name / "audit"
        a.mkdir(parents=True, exist_ok=True)
        (a / shard).write_text("# AI-DLC Audit Log\n\n" + ledger)

    def activate(self, name):
        (self.intents / "active-intent").write_text(name + "\n")

    def run(self, **kw):
        kw.setdefault("env", {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
                              "CLAUDE_CODE_SESSION_ID": "S1"})
        kw.setdefault("run_aidlc", fake_aidlc())
        kw.setdefault("home", self.root / "no-home")
        checks = pf.run_checks("claude-code", self.root, kw.pop("require_human_turn", True), kw.pop("mode", "setup"), **kw)
        return {c["name"]: c for c in checks}


APPROVED_LEDGER = (
    ev("HUMAN_TURN", "2026-01-01T10:00:00Z", Session="S1")
    + ev("DECISION_RECORDED", "2026-01-01T10:05:00Z", Stage="code-generation", Checkpoint="plan-approval", Session="S1")
    + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1")
    + ev("PLAN_APPROVAL_RECORDED", "2026-01-01T10:06:01Z", Stage="code-generation", Session="S1",
         Checkpoint="Code Generation Plan Approval")
)


class HumanTurnScoping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_active_workflow_passes(self):
        self.ws.intent("run-a", APPROVED_LEDGER)
        self.ws.activate("run-a")
        r = self.ws.run()
        self.assertEqual(r["active-workflow"]["status"], "PASS")
        self.assertEqual(r["human-turn-recorded"]["status"], "PASS", r["human-turn-recorded"]["detail"])

    def test_unrelated_workflow_human_turn_is_rejected(self):
        # The OTHER workflow has genuine-looking turns; the active one has none.
        self.ws.intent("other", ev("HUMAN_TURN", "2026-01-01T09:00:00Z", Session="S1"))
        self.ws.intent("active", ev("STAGE_STARTED", "2026-01-01T10:00:00Z", Stage="intent-capture"))
        self.ws.activate("active")
        r = self.ws.run()
        self.assertEqual(r["human-turn-recorded"]["status"], "FAIL")
        self.assertIn("no HUMAN_TURN", r["human-turn-recorded"]["detail"])

    def test_missing_active_cursor_fails_even_if_other_ledgers_have_turns(self):
        self.ws.intent("other", APPROVED_LEDGER)
        r = self.ws.run()
        self.assertEqual(r["active-workflow"]["status"], "FAIL")
        self.assertNotIn("human-turn-recorded", r)

    def test_cursor_to_missing_record_fails(self):
        self.ws.activate("ghost")
        self.assertEqual(self.ws.run()["active-workflow"]["status"], "FAIL")

    def test_plan_approval_without_preceding_turn_fails(self):
        led = (ev("HUMAN_TURN", "2026-01-01T09:00:00Z", Session="S1")
               + ev("DECISION_RECORDED", "2026-01-01T10:05:00Z", Checkpoint="plan-approval", Session="S1")
               + ev("PLAN_APPROVAL_RECORDED", "2026-01-01T10:06:00Z", Session="S1"))
        self.ws.intent("w", led)
        self.ws.activate("w")
        r = self.ws.run()
        self.assertEqual(r["human-turn-recorded"]["status"], "FAIL")
        self.assertIn("not preceded", r["human-turn-recorded"]["detail"])

    def test_plan_approval_backed_only_by_other_session_fails(self):
        led = (ev("DECISION_RECORDED", "2026-01-01T10:05:00Z", Checkpoint="plan-approval", Session="S1")
               + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S2")
               + ev("PLAN_APPROVAL_RECORDED", "2026-01-01T10:06:01Z", Session="S1"))
        self.ws.intent("w", led)
        self.ws.activate("w")
        self.assertEqual(self.ws.run()["human-turn-recorded"]["status"], "FAIL")

    def test_human_turn_after_plan_approval_does_not_count(self):
        led = (ev("DECISION_RECORDED", "2026-01-01T10:05:00Z", Checkpoint="plan-approval", Session="S1")
               + ev("PLAN_APPROVAL_RECORDED", "2026-01-01T10:06:00Z", Session="S1")
               + ev("HUMAN_TURN", "2026-01-01T10:07:00Z", Session="S1"))
        self.ws.intent("w", led)
        self.ws.activate("w")
        self.assertEqual(self.ws.run()["human-turn-recorded"]["status"], "FAIL")

    def test_malformed_timestamp_fails(self):
        self.ws.intent("w", ev("HUMAN_TURN", "yesterday", Session="S1"))
        self.ws.activate("w")
        r = self.ws.run()
        self.assertEqual(r["human-turn-recorded"]["status"], "FAIL")
        self.assertIn("malformed", r["human-turn-recorded"]["detail"])

    def test_human_turn_without_session_fails(self):
        self.ws.intent("w", ev("HUMAN_TURN", "2026-01-01T10:00:00Z"))
        self.ws.activate("w")
        self.assertEqual(self.ws.run()["human-turn-recorded"]["status"], "FAIL")

    def test_empty_ledger_fails(self):
        (self.ws.intents / "w").mkdir()
        self.ws.activate("w")
        self.assertEqual(self.ws.run()["human-turn-recorded"]["status"], "FAIL")

    def test_session_mode_requires_turn_from_current_session(self):
        self.ws.intent("w", ev("HUMAN_TURN", "2026-01-01T10:00:00Z", Session="OLD"))
        self.ws.activate("w")
        r = self.ws.run(require_human_turn=False, mode="session")
        self.assertEqual(r["human-turn-recorded"]["status"], "FAIL")


def handback(ts_done, ts_turn, session="S1", **turn_fields):
    """A sub-agent hand-back as Claude Code records it: SUBAGENT_COMPLETED,
    then the queued hand-back prompt minting a HUMAN_TURN."""
    return (ev("SUBAGENT_COMPLETED", ts_done, **{"Agent Type": "aidlc-developer-agent"})
            + ev("HUMAN_TURN", ts_turn, Session=session, **turn_fields))


GENUINE = ev("HUMAN_TURN", "2026-01-01T09:00:00Z", Session="S1")
PLAN_PROMPT = ev("DECISION_RECORDED", "2026-01-01T10:05:00Z", Stage="code-generation",
                 Checkpoint="plan-approval", Session="S1")
PLAN_OK = ev("PLAN_APPROVAL_RECORDED", "2026-01-01T10:06:01Z", Stage="code-generation",
             Session="S1", Details="Approve Plan")


class HandBackIntegrity(unittest.TestCase):
    """Sub-agent hand-backs must never back an approval-sensitive event, and a
    genuine human turn must not be rejected because hand-backs happened."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, ledger):
        self.ws.intent("w", ledger)
        self.ws.activate("w")
        return self.ws.run()["human-turn-recorded"]

    # ---- false acceptance: hand-back turns alone must FAIL ----

    def test_plan_approval_backed_only_by_handback_fails(self):
        r = self.check(GENUINE + PLAN_PROMPT + handback("2026-01-01T10:06:00Z", "2026-01-01T10:06:01Z") + PLAN_OK)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("coincide with sub-agent hand-backs", r["detail"])

    def test_plan_approval_backed_by_explicit_envelope_origin_fails(self):
        led = (GENUINE + PLAN_PROMPT
               + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1", Origin="harness-envelope") + PLAN_OK)
        self.assertEqual(self.check(led)["status"], "FAIL")

    def test_handback_in_same_second_as_completion_fails(self):
        r = self.check(GENUINE + PLAN_PROMPT + handback("2026-01-01T10:06:00Z", "2026-01-01T10:06:00Z") + PLAN_OK)
        self.assertEqual(r["status"], "FAIL")

    def test_stage_approval_backed_only_by_handback_fails(self):
        led = (GENUINE + ev("QUESTION_ANSWERED", "2026-01-01T09:30:00Z", Stage="code-generation")
               + ev("STAGE_AWAITING_APPROVAL", "2026-01-01T10:00:00Z", Stage="code-generation")
               + handback("2026-01-01T10:01:00Z", "2026-01-01T10:01:01Z")
               + ev("GATE_APPROVED", "2026-01-01T10:01:05Z", Stage="code-generation", **{"User Input": "Approve"}))
        r = self.check(led)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("stage approval", r["detail"])

    def test_request_changes_backed_only_by_handback_fails(self):
        led = (GENUINE + ev("QUESTION_ANSWERED", "2026-01-01T09:30:00Z", Stage="domain-design")
               + ev("STAGE_AWAITING_APPROVAL", "2026-01-01T10:00:00Z", Stage="domain-design")
               + handback("2026-01-01T10:01:00Z", "2026-01-01T10:01:02Z")
               + ev("GATE_REJECTED", "2026-01-01T10:01:05Z", Stage="domain-design",
                    **{"User Input": "Request Changes"}))
        r = self.check(led)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("Request Changes", r["detail"])

    def test_autonomous_switch_backed_only_by_handback_fails(self):
        led = (GENUINE + ev("QUESTION_ANSWERED", "2026-01-01T10:00:00Z", Stage="code-generation")
               + handback("2026-01-01T10:01:00Z", "2026-01-01T10:01:01Z")
               + ev("AUTONOMY_MODE_SET", "2026-01-01T10:01:03Z", Mode="autonomous"))
        r = self.check(led)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("autonomous-mode switch", r["detail"])

    def test_handback_turn_after_resolution_does_not_back_next_gate_alone(self):
        # A genuine turn was consumed by the earlier answer; only a hand-back follows.
        led = (ev("HUMAN_TURN", "2026-01-01T10:00:00Z", Session="S1")
               + ev("QUESTION_ANSWERED", "2026-01-01T10:00:05Z", Stage="code-generation")
               + handback("2026-01-01T10:02:00Z", "2026-01-01T10:02:01Z")
               + ev("GATE_APPROVED", "2026-01-01T10:02:10Z", Stage="code-generation", **{"User Input": "Approve"}))
        self.assertEqual(self.check(led)["status"], "FAIL")

    def test_only_handback_turns_in_workflow_fails(self):
        r = self.check(handback("2026-01-01T10:00:00Z", "2026-01-01T10:00:01Z"))
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("no genuine human turn", r["detail"])

    # ---- false rejection: genuine turns must still PASS ----

    def test_genuine_turn_with_handbacks_beside_it_passes(self):
        led = (GENUINE + PLAN_PROMPT
               + handback("2026-01-01T10:05:10Z", "2026-01-01T10:05:11Z")
               + ev("HUMAN_TURN", "2026-01-01T10:05:40Z", Session="S1")
               + handback("2026-01-01T10:05:50Z", "2026-01-01T10:05:51Z")
               + PLAN_OK)
        r = self.check(led)
        self.assertEqual(r["status"], "PASS", r["detail"])
        self.assertIn("2 excluded as sub-agent hand-backs", r["detail"])

    def test_picker_origin_right_after_handback_passes(self):
        led = (GENUINE + PLAN_PROMPT + ev("SUBAGENT_COMPLETED", "2026-01-01T10:06:00Z")
               + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1", Origin="question-picker") + PLAN_OK)
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_upstream_person_origin_right_after_handback_passes(self):
        led = (GENUINE + PLAN_PROMPT + ev("SUBAGENT_COMPLETED", "2026-01-01T10:06:00Z")
               + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1", Origin="person", Source="typed") + PLAN_OK)
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_upstream_host_turn_never_backs_an_approval(self):
        led = (GENUINE + PLAN_PROMPT
               + ev("HOST_TURN", "2026-01-01T10:06:00Z", Session="S1", Origin="host",
                    Reason="claude sub-agent hand-back", Source="template") + PLAN_OK)
        r = self.check(led)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("not preceded", r["detail"])

    def test_turn_outside_handback_window_passes(self):
        led = (GENUINE + PLAN_PROMPT + ev("SUBAGENT_COMPLETED", "2026-01-01T10:05:57Z")
               + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1") + PLAN_OK)
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_turn_recorded_before_completion_in_same_second_passes(self):
        led = (GENUINE + PLAN_PROMPT + ev("HUMAN_TURN", "2026-01-01T10:06:00Z", Session="S1")
               + ev("SUBAGENT_COMPLETED", "2026-01-01T10:06:00Z") + PLAN_OK)
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_genuine_stage_gate_and_request_changes_pass(self):
        led = (GENUINE
               + ev("HUMAN_TURN", "2026-01-01T10:01:00Z", Session="S1")
               + ev("GATE_REJECTED", "2026-01-01T10:01:02Z", Stage="d", **{"User Input": "Request Changes"})
               + handback("2026-01-01T10:02:00Z", "2026-01-01T10:02:01Z")
               + ev("HUMAN_TURN", "2026-01-01T10:03:00Z", Session="S1")
               + ev("GATE_APPROVED", "2026-01-01T10:03:02Z", Stage="d", **{"User Input": "Approve"}))
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_autonomous_gate_after_human_backed_grant_is_exempt(self):
        led = (GENUINE + ev("HUMAN_TURN", "2026-01-01T10:00:00Z", Session="S1")
               + ev("AUTONOMY_MODE_SET", "2026-01-01T10:00:02Z", Mode="autonomous")
               + handback("2026-01-01T10:05:00Z", "2026-01-01T10:05:01Z")
               + ev("GATE_APPROVED", "2026-01-01T10:05:05Z", Stage="code-generation"))
        self.assertEqual(self.check(led)["status"], "PASS")

    def test_live_control_sequence_passes(self):
        # Timings of the 2026-10-10 live positive control (identifiers synthetic).
        led = (ev("DECISION_RECORDED", "2026-10-10T03:17:19Z", Checkpoint="Code Generation Plan Approval", Session="S1")
               + ev("HUMAN_TURN", "2026-10-10T03:18:27Z", Session="S1")
               + ev("PLAN_APPROVAL_RECORDED", "2026-10-10T03:18:32Z", Session="S1", Details="Approve Plan")
               + handback("2026-10-10T03:19:18Z", "2026-10-10T03:19:19Z")
               + handback("2026-10-10T03:21:02Z", "2026-10-10T03:21:02Z")
               + handback("2026-10-10T03:22:06Z", "2026-10-10T03:22:07Z")
               + ev("QUESTION_ANSWERED", "2026-10-10T04:06:27Z", Stage="code-generation")
               + ev("HUMAN_TURN", "2026-10-10T04:06:49Z", Session="S1")
               + ev("GATE_APPROVED", "2026-10-10T04:07:01Z", Stage="code-generation", **{"User Input": "Approve"}))
        r = self.check(led)
        self.assertEqual(r["status"], "PASS", r["detail"])
        self.assertIn("3 excluded", r["detail"])


class CommittedRealLedgers(unittest.TestCase):
    """The committed Run B and live-control ledgers must still pass the
    hardened check (they are read, never modified)."""

    def test_committed_ledgers_pass(self):
        intents = REPO / "aidlc" / "spaces" / "default" / "intents"
        for name in ("261008-aicc-catalog-claude", "261010-cert-live-control"):
            rec = intents / name
            if not rec.is_dir():
                self.skipTest(f"{name} not present in this checkout")
            events, err = pf.load_intent_events(rec)
            self.assertIsNone(err)
            ok, detail = pf.check_human_turn_evidence(events)
            self.assertTrue(ok, f"{name}: {detail}")


class EnvironmentControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def setup_checks(self, **kw):
        return self.ws.run(require_human_turn=False, mode="setup", **kw)

    def test_fresh_clone_setup_passes(self):
        r = self.setup_checks()
        self.assertTrue(all(c["status"] == "PASS" for c in r.values() if c["required"]), r)

    def test_missing_mandatory_hook_fails(self):
        s = json.loads(json.dumps(GOOD_SETTINGS))
        del s["hooks"]["UserPromptSubmit"]
        self.ws.settings(s)
        r = self.setup_checks()
        self.assertEqual(r["approval-hook"]["status"], "FAIL")
        self.assertIn("UserPromptSubmit", r["approval-hook"]["detail"])

    def test_plan_guard_on_wrong_matcher_fails(self):
        s = json.loads(json.dumps(GOOD_SETTINGS))
        s["hooks"]["PreToolUse"][0]["matcher"] = "Read"
        self.ws.settings(s)
        self.assertEqual(self.setup_checks()["approval-hook"]["status"], "FAIL")

    def test_disable_all_hooks_in_local_settings_fails(self):
        self.ws.settings({"disableAllHooks": True}, name="settings.local.json")
        self.assertEqual(self.setup_checks()["hooks-not-disabled"]["status"], "FAIL")

    def test_unattended_env_fails(self):
        r = self.setup_checks(env={"AIDLC_UNATTENDED": "1"})
        self.assertEqual(r["attended-mode"]["status"], "FAIL")

    def test_inherited_protected_state_fails_in_setup(self):
        (self.ws.root / "aidlc" / ".aidlc-clone-id").write_text("x")
        self.assertEqual(self.setup_checks()["fresh-clone-isolation"]["status"], "FAIL")

    def test_version_outside_policy_fails(self):
        r = self.setup_checks(run_aidlc=fake_aidlc(version="aidlc 2.9.4"))
        self.assertEqual(r["aidlc-runtime"]["status"], "FAIL")

    def test_doctor_reporting_hooks_never_executed_fails(self):
        r = self.setup_checks(run_aidlc=fake_aidlc(doctor="fail  Hooks have never executed\n0 problems"))
        self.assertEqual(r["aidlc-doctor"]["status"], "FAIL")

    def test_missing_runtime_fails(self):
        self.assertEqual(self.setup_checks(run_aidlc=lambda a, c: None)["aidlc-runtime"]["status"], "FAIL")


class SurfaceDetection(unittest.TestCase):
    def test_surfaces(self):
        self.assertEqual(pf.detect_claude_surface({})[0], "NOT_DETECTED")
        self.assertEqual(pf.detect_claude_surface({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})[0], "VERIFIED")
        self.assertEqual(pf.detect_claude_surface({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"})[0], "UNVERIFIED")
        self.assertEqual(pf.detect_claude_surface({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})[0], "UNSUPPORTED")
        self.assertEqual(pf.detect_claude_surface({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "remote"})[0], "UNSUPPORTED")

    def test_session_mode_outside_claude_fails(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Workspace(t)
            ws.intent("w", APPROVED_LEDGER)
            ws.activate("w")
            r = ws.run(env={}, require_human_turn=False, mode="session")
            self.assertEqual(r["execution-surface"]["status"], "FAIL")

    def test_unsupported_surface_fails_human_turn_mode(self):
        with tempfile.TemporaryDirectory() as t:
            ws = Workspace(t)
            ws.intent("w", APPROVED_LEDGER)
            ws.activate("w")
            r = ws.run(env={"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "sdk-ts"})
            self.assertEqual(r["execution-surface"]["status"], "FAIL")


class InstalledHarnessMatchesPolicy(unittest.TestCase):
    """The committed .claude/settings.json must carry every mandatory hook."""

    def test_repo_settings_have_mandatory_hooks(self):
        settings = REPO / ".claude" / "settings.json"
        if not settings.is_file():
            self.skipTest("Claude harness not installed in this checkout")
        self.assertEqual(pf.missing_claude_hooks(json.loads(settings.read_text())), [])

    def test_cli_usage_error(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "preflight.py")], capture_output=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
