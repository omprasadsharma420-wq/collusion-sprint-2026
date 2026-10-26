"""End-to-end transport/replay fixture; outputs are scripted and never research data."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from v8.protocol import MODEL_NAME, MODEL_REVISION, VLLM_VERSION
from v8.run_r import run_episode
from v8.transport import V8Transport


class ScriptedProvider:
    def __init__(self, extra_message=False):
        self.next_id = 0
        self.extra_message = extra_message

    def __call__(self, request: bytes) -> dict:
        self.next_id += 1
        wire = json.loads(request)
        if "response_format" in wire:
            content = json.loads(wire["messages"][-1]["content"])
            answer = {"cutoff_event_id": content["cutoff_event_id"],
                      "candidate_label": "NO_CONCERN", "evidence_event_ids": [],
                      "rationale": "Software fixture", "suspected_rule": "NONE",
                      "observation_basis": "WRITE_ONLY"}
            message = {"role": "assistant", "content": json.dumps(answer)}
            finish = "stop"
        elif (self.extra_message and len([item for item in wire["messages"]
                                          if item.get("role") == "tool"]) == 1):
            message = {"role": "assistant", "content": "", "tool_calls": [{
                "id": "fixture-tool-2", "type": "function", "function": {
                    "name": "post_team_update", "arguments": json.dumps({
                        "message": "Fixture status update"})}}]}
            finish = "tool_calls"
        elif any(item.get("role") == "tool" for item in wire["messages"]):
            message = {"role": "assistant", "content": "Fixture finalized."}
            finish = "stop"
        else:
            message = {"role": "assistant", "content": "", "tool_calls": [{
                "id": "fixture-tool-1", "type": "function", "function": {
                    "name": "review_t4", "arguments": json.dumps({
                        "decision": "accept_assessment", "reason": "Fixture check"})}}]}
            finish = "tool_calls"
        body = json.dumps({"id": f"fixture-{self.next_id}", "model": MODEL_NAME,
                           "choices": [{"index": 0, "message": message,
                                        "finish_reason": finish}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                     "total_tokens": 2}}).encode()
        return {"status": 200, "body": body, "model": MODEL_NAME,
                "revision": MODEL_REVISION, "vllm_version": VLLM_VERSION}


class OfflineRRunnerTests(unittest.TestCase):
    def test_model_authored_additional_message_does_not_fail_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = V8Transport(ScriptedProvider(extra_message=True),
                                    root / "provider_calls/study", max_calls=4)
            record, validation = run_episode(root, 1, 1, "R0_BENIGN", transport,
                                             source_commit="OFFLINE_FIXTURE",
                                             started=time.monotonic())
            self.assertEqual(record["B_responses"], 3)
            self.assertTrue(validation["validation_ok"], validation)
            messages = json.loads((root / record["episode_key"] /
                                   "trusted/messages.json").read_text())
            self.assertEqual(len(messages), 2)

    def test_complete_pair_and_receipt_join(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = ScriptedProvider()
            transport = V8Transport(provider, root / "provider_calls/study", max_calls=6)
            predecision = []
            for index, condition in enumerate(("R0_BENIGN", "R1_UNAUTHORIZED"), 1):
                record, validation = run_episode(root, index, 1, condition, transport,
                                                 source_commit="OFFLINE_FIXTURE",
                                                 started=time.monotonic())
                self.assertEqual(record["status"], "ALL_FINAL")
                self.assertTrue(validation["validation_ok"], validation)
                self.assertEqual(record["B_responses"], 2)
                self.assertTrue(record["lawful_hold_acceptance"])
                episode = root / record["episode_key"]
                offsets = json.loads((episode / "trusted/notification_input_offsets.json").read_text())
                self.assertEqual(len(offsets), 1)
                raw = (episode / "trusted" / offsets[0]["model_input_ref"]).read_bytes()
                self.assertIn(b"WORKSPACE_NOTIFICATION", raw[offsets[0]["byte_start"]:
                                                             offsets[0]["byte_end"]])
                predecision.append((episode / "auditor/m0_predecision.json").read_bytes())
            self.assertEqual(predecision[0], predecision[1])
            self.assertEqual(transport.call_count, 6)


if __name__ == "__main__":
    unittest.main()
