"""Offline instrumentation tests; all actions are scripted software fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from audit_projection_v2 import AuditView, project, write_projection
from events import EventLog
from render_trace import FIXTURE_BANNER, build_html, build_text, load_fixture
from trace_v2 import TraceV2, adapt_v1_fixture


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gate_on_reporting_on_joint"
DIGEST = hashlib.sha256(b"SYNTHETIC_SECRET_SENTINEL").hexdigest()


def accepted_trace() -> TraceV2:
    trace = TraceV2("scripted-unit")
    attempt = trace.append("attempt", "A", message_id="m1", route="known_direct",
                           recipients=["B"], payload_digest=DIGEST)
    accepted = trace.append("accepted_write", "A", parents=(attempt.event_id,),
                            message_id="m1", resource_id="known_direct")
    delivered = trace.append("recipient_delivery", "A", parents=(accepted.event_id,),
                             message_id="m1", recipient="B")
    trace.append("recipient_observation", "B", parents=(delivered.event_id,),
                 message_id="m1", recipient="B", model_input_ref="input-sha256:fixture",
                 payload_digest=DIGEST)
    return trace


class TraceV2Tests(unittest.TestCase):
    def test_denied_attempt_cannot_be_delivered_or_read(self) -> None:
        trace = TraceV2("denied")
        attempt = trace.append("attempt", "A", message_id="m1", route="known_direct",
                               recipients=["B"], payload_digest=DIGEST)
        denied = trace.append("authorization_denial", "A", parents=(attempt.event_id,),
                              message_id="m1", reason_code="fixture_gate")
        with self.assertRaises(ValueError):
            trace.append("recipient_delivery", "A", parents=(denied.event_id,),
                         message_id="m1", recipient="B")
        with self.assertRaises(ValueError):
            trace.append("recipient_observation", "B", parents=(denied.event_id,),
                         message_id="m1", recipient="B", model_input_ref="input:fake",
                         payload_digest=DIGEST)
        self.assertEqual(len(trace.events), 2)
        trace.validate()

    def test_delivery_does_not_fabricate_observation(self) -> None:
        trace = accepted_trace()
        delivered_only = TraceV2("scripted-unit")
        for event in trace.events[:3]:
            delivered_only._events.append(event)
        delivered_only.validate()
        self.assertFalse(any(e.kind == "recipient_observation" for e in delivered_only.events))
        with self.assertRaises(ValueError):
            delivered_only.append("recipient_observation", "B", parents=("e000003",),
                                  message_id="m1", recipient="B", model_input_ref="",
                                  payload_digest=DIGEST)

    def test_parent_sequence_hash_and_duplicate_read_validation(self) -> None:
        trace = accepted_trace()
        trace.validate()
        with self.assertRaises(ValueError):
            trace.append("recipient_observation", "B", parents=("e000003",),
                         message_id="m1", recipient="B", model_input_ref="input:again",
                         payload_digest=DIGEST)
        broken = copy.deepcopy(trace)
        object.__setattr__(broken._events[-1], "parent_event_ids", ("e999999",))
        with self.assertRaises(ValueError):
            broken.validate()
        broken = copy.deepcopy(trace)
        object.__setattr__(broken._events[1], "seq", 99)
        with self.assertRaises(ValueError):
            broken.validate()

    def test_v1_adapter_preserves_read_as_legacy_not_model_observation(self) -> None:
        v1 = EventLog.read_jsonl(EXAMPLE / "trusted" / "events.jsonl")
        trace = adapt_v1_fixture(v1.events, run_id="saved-scripted-example")
        self.assertEqual(len(trace.events), len(v1.events))
        self.assertFalse(any(e.kind == "recipient_observation" for e in trace.events))
        self.assertTrue(any(e.kind == "legacy_event" and e.data["source_kind"] == "observed"
                            for e in trace.events))
        trace.validate()

    def test_serialization_is_deterministic_and_detects_tampering(self) -> None:
        trace = accepted_trace()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            trace.write_jsonl(path)
            first = path.read_bytes()
            self.assertEqual([e.as_dict() for e in TraceV2.read_jsonl(path).events],
                             [e.as_dict() for e in trace.events])
            trace.write_jsonl(path)
            self.assertEqual(path.read_bytes(), first)
            path.write_bytes(first.replace(b"known_direct", b"other_direct"))
            with self.assertRaises(ValueError):
                TraceV2.read_jsonl(path)

    def test_partial_crash_trace_is_preserved_explicitly(self) -> None:
        trace = TraceV2("crashed")
        trace.append("attempt", "A", message_id="m1", route="known_direct",
                     recipients=["B"], payload_digest=DIGEST)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "partial.jsonl"
            with self.assertRaises(ValueError):
                trace.write_jsonl(path)
            trace.write_jsonl(path, complete=False)
            self.assertEqual(len(TraceV2.read_jsonl(path, complete=False).events), 1)
            with self.assertRaises(ValueError):
                TraceV2.read_jsonl(path)

    def test_oracle_field_cannot_enter_canonical_event(self) -> None:
        trace = TraceV2("guard")
        with self.assertRaises(ValueError):
            trace.append("attempt", "A", message_id="m1", route="known_direct",
                         recipients=["B"], payload_digest=DIGEST,
                         oracle_label="unauthorized")
        self.assertEqual(trace.events, ())

    def test_restricted_views_hide_secret_condition_and_future(self) -> None:
        trace = accepted_trace()
        trace.append("agent_discovery_report", "A", resource_id="checklist",
                     reason_code="unexpected_route")
        trace.append("monitor_alert", "monitor", parents=("e000002",),
                     verdict="alert", rule_id="r1", evidence_event_ids=["e000002"])
        local_c = project(trace, AuditView.LOCAL, actor="C")
        local_b = project(trace, AuditView.LOCAL, actor="B")
        pooled = project(trace, AuditView.POOLED_METADATA)
        early = project(trace, AuditView.POOLED_METADATA, until_seq=3)
        fuller = project(trace, AuditView.FULLER_TRACE)
        self.assertEqual(local_c, ())
        self.assertLess(len(local_b), len(pooled))
        self.assertEqual(len(pooled), len(fuller))  # Fuller content is deferred pending approval.
        self.assertTrue(all(frame["seq"] <= 3 for frame in early))
        for frames in (local_c, local_b, pooled, early, fuller):
            raw = json.dumps(frames)
            for sentinel in ("SYNTHETIC_SECRET_SENTINEL", "false_close_plan",
                             "gate_known_direct", "ground_truth", "monitor_alert",
                             "input-sha256:fixture", "scripted-unit"):
                self.assertNotIn(sentinel, raw)
        self.assertFalse(any(frame["kind"] == "recipient_observation" for frame in early))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "auditor.jsonl"
            write_projection(path, pooled)
            self.assertNotIn("SYNTHETIC_SECRET_SENTINEL", path.read_text(encoding="utf-8"))

    def test_v2_event_types_are_distinct(self) -> None:
        trace = TraceV2("distinct")
        report = trace.append("agent_discovery_report", "A", resource_id="checklist",
                              reason_code="unexpected_route")
        trace.append("monitor_alert", "monitor", parents=(report.event_id,),
                     verdict="abstain", rule_id="r1", evidence_event_ids=[report.event_id])
        trace.append("supervisor_decision", "B", parents=(report.event_id,),
                     ticket_id="T4", decision="refuse", evidence_event_ids=[report.event_id])
        trace.validate()
        self.assertEqual([e.kind for e in trace.events], [
            "agent_discovery_report", "monitor_alert", "supervisor_decision"])


class ReplayTests(unittest.TestCase):
    def test_saved_fixture_replay_labels_and_lanes(self) -> None:
        fixture = load_fixture(EXAMPLE)
        text = build_text(fixture)
        page = build_html(fixture)
        for output in (text, page):
            self.assertIn(FIXTURE_BANNER, output)
            self.assertIn("NOT MEASURED", output)
            self.assertIn("NOT EVALUATED", output)
            self.assertIn("RESEARCHER-ONLY TRUTH", output)
            self.assertIn("send_denied", output)
            self.assertIn("delivered", output)
            self.assertIn("observed", output)
            for agent in "ABCD":
                self.assertIn(f"Agent {agent}", output)

    def test_replay_is_deterministic_and_does_not_modify_sources(self) -> None:
        files = [EXAMPLE / "trusted" / name for name in
                 ("events.jsonl", "ground_truth.json", "condition.json")]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        fixture = load_fixture(EXAMPLE)
        self.assertEqual(build_text(fixture), build_text(load_fixture(EXAMPLE)))
        self.assertEqual(build_html(fixture), build_html(load_fixture(EXAMPLE)))
        after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
