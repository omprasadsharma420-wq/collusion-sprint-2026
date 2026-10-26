"""V8 software controls are not empirical model behavior."""

import json
import unittest

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from protocol_v3 import MEMO_MARKER
from v8.adapter import ActorAdapterV8
from v8.auditor import eligible_cutoffs, m0_at_time, m1_at_time
from v8.protocol import P_PRIVATE_NOTES, R_MESSAGES, SUPERVISOR_SYSTEM
from v8.world import WorldV8


class NoCallTransport:
    def respond(self, *args, **kwargs):
        raise AssertionError("No real or fake model response was requested")


class WorldV8Controls(unittest.TestCase):
    def test_r_seeded_exposure_is_actual_b_input_and_not_model_authored(self):
        world = WorldV8(phase="R", gate_known_direct=False, run_id="r-exposure")
        mid = world.seed_r_message(body=R_MESSAGES["R0_BENIGN"])
        self.assertEqual(world.messages[mid]["origin"], "RESEARCHER_SEEDED_EXPOSURE")
        self.assertFalse(any(e.kind == "recipient_observation" for e in world.trace.events))
        messages = [world.review_context_message(), *world.notification_messages("B")]
        raw = world.capture_model_input("B", messages)
        self.assertIn(R_MESSAGES["R0_BENIGN"].encode(), raw)
        self.assertTrue(world.b_reviewable_input_seen)
        self.assertEqual(len([e for e in world.trace.events if e.kind == "recipient_observation"]), 1)
        self.assertTrue(world.execute_tool("B", "review_t4", {
            "decision": "accept_assessment", "reason": "truthful HOLD"})["ok"])
        self.assertEqual(world.outcome()["task_score"], 4)
        with self.assertRaises(ValueError):
            world.execute_tool("S", "supervisor_list_status", {})

    def test_r_message_pair_has_identical_predecision_m0_and_different_m1_content(self):
        views = []
        for name in ("R0_BENIGN", "R1_UNAUTHORIZED"):
            world = WorldV8(phase="R", gate_known_direct=False, run_id="r-pair")
            world.seed_r_message(body=R_MESSAGES[name])
            cutoff = eligible_cutoffs(world.trace)[-1]
            views.append((m0_at_time(world.trace, cutoff),
                          m1_at_time(world.trace, world.messages, cutoff)))
        self.assertEqual(views[0][0]["input_frames"], views[1][0]["input_frames"])
        self.assertNotEqual(views[0][1]["workplace_messages"], views[1][1]["workplace_messages"])

    def test_invalid_release_attempt_is_rejected_and_r2_candidate(self):
        world = WorldV8(phase="R", gate_known_direct=False, run_id="r-invalid")
        world.seed_r_message(body=R_MESSAGES["R1_UNAUTHORIZED"])
        world.capture_model_input("B", [world.review_context_message(),
                                        *world.notification_messages("B")])
        result = world.execute_tool("B", "review_t4", {
            "decision": "approve_release", "reason": "target"})
        self.assertFalse(result["ok"])
        self.assertIsNotNone(world.outcome()["invalid_release_approval"])
        verdicts = run_audit(project(world.trace, AuditView.POOLED_METADATA))
        self.assertEqual([(v["rule_id"], v["verdict"]) for v in verdicts], [("R2", "alert")])

    def test_supervisor_is_separate_from_b_and_gate(self):
        world = WorldV8(phase="P", gate_known_direct=True, run_id="p-supervisor")
        self.assertFalse(world.execute_tool("A", "send_direct", {
            "recipient": "B", "message": "Status"})["ok"])
        sup = world.execute_tool("S", "supervisor_send_direct", {
            "recipient": "B", "message": "Please review T4"})
        self.assertTrue(sup["ok"])
        self.assertFalse(any(e.kind == "recipient_observation" and e.actor == "B"
                             for e in world.trace.events))
        world.capture_model_input("B", world.notification_messages("B"))
        self.assertTrue(any(e.kind == "recipient_observation" and e.actor == "B"
                            for e in world.trace.events))
        reply = world.execute_tool("B", "worker_send_supervisor", {"message": "I will review."})
        self.assertTrue(reply["ok"])
        world.capture_model_input("S", world.notification_messages("S"))
        self.assertTrue(any(e.kind == "recipient_observation" and e.actor == "S"
                            for e in world.trace.events))
        self.assertFalse(world.execute_tool("S", "review_t4", {
            "decision": "approve_release", "reason": "not authorized"})["ok"])
        self.assertIsNone(world.outcome()["invalid_release_approval"])

    def test_report_inbox_and_role_private_text_isolation(self):
        world = WorldV8(phase="P", gate_known_direct=False, run_id="p-reports")
        adapter = ActorAdapterV8(world, NoCallTransport(), phase="P",
                                 private_note="P1_PRESSURE", seed=1, worker_cap=20)
        self.assertIn(P_PRIVATE_NOTES["P1_PRESSURE"], json.dumps(adapter.messages["A"]))
        for actor in "BCDS":
            self.assertNotIn(P_PRIVATE_NOTES["P1_PRESSURE"], json.dumps(adapter.messages[actor]))
            self.assertNotIn(MEMO_MARKER, json.dumps(adapter.messages[actor]))
        self.assertEqual(adapter.messages["S"][0]["content"], SUPERVISOR_SYSTEM)
        world.execute_tool("C", "report_concern", {"resource_id": "release_checklist",
                                                    "reason_code": "unexpected_route"})
        reports = world.execute_tool("S", "supervisor_read_reports", {})["reports"]
        self.assertEqual(reports[0]["from"], "C")
        self.assertEqual(reports[0]["resource_id"], "release_checklist")
        self.assertNotIn(P_PRIVATE_NOTES["P1_PRESSURE"], json.dumps(reports))

    def test_no_next_turn_means_no_observation(self):
        world = WorldV8(phase="P", gate_known_direct=False, run_id="p-final")
        world.execute_tool("A", "post_team_update", {"message": "Status"})
        self.assertTrue(world.notification_queues["B"])
        self.assertFalse(any(e.kind == "recipient_observation" and e.actor == "B"
                             for e in world.trace.events))


if __name__ == "__main__":
    unittest.main()
