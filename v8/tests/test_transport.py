import json
import tempfile
import unittest
from pathlib import Path

from v8.protocol import (M1_OUTPUT_SCHEMA, MAX_STUDY_RESPONSES, MAX_TOTAL_RESPONSES,
                         P_SCHEDULE, R_SCHEDULE, R_WORKER_TOOLS)
from v8.transport import V8Transport, request_bytes, validate_m1


class TransportV8Tests(unittest.TestCase):
    def test_fixed_balanced_counts_and_budget(self):
        self.assertEqual(len(R_SCHEDULE), 24)
        self.assertEqual(len(P_SCHEDULE), 40)
        self.assertEqual(MAX_STUDY_RESPONSES, 4232)
        self.assertEqual(MAX_TOTAL_RESPONSES, 4240)
        for block in range(1, 13):
            self.assertEqual({condition for b, condition in R_SCHEDULE if b == block},
                             {"R0_BENIGN", "R1_UNAUTHORIZED"})
        for block in range(1, 11):
            self.assertEqual({arm for b, arm in P_SCHEDULE if b == block},
                             {"P0_G0", "P0_G1", "P1_G0", "P1_G1"})

    def test_distinct_worker_supervisor_and_m1_wire_contracts(self):
        captured = {"messages": [{"role": "user", "content": "test"}], "tools": R_WORKER_TOOLS}
        worker = json.loads(request_bytes(captured, seed=1, kind="worker"))
        self.assertEqual(worker["tools"], R_WORKER_TOOLS)
        self.assertEqual(worker["tool_choice"], "auto")
        m1 = json.loads(request_bytes({"messages": captured["messages"]}, seed=1, kind="m1"))
        self.assertEqual(m1["response_format"]["json_schema"]["schema"], M1_OUTPUT_SCHEMA)
        self.assertNotIn("tools", m1)
        with self.assertRaises(ValueError):
            request_bytes(captured, seed=1, kind="m1")

    def test_m1_output_rejects_future_or_missing_evidence(self):
        base = {"cutoff_event_id": "e000010", "candidate_label": "NO_CONCERN",
                "evidence_event_ids": ["e000010"], "rationale": "No concern in the visible slice.",
                "suspected_rule": "NONE", "observation_basis": "WRITE_ONLY"}
        validate_m1(base, cutoff="e000010", allowed_event_ids={"e000010"})
        with self.assertRaises(ValueError):
            validate_m1({**base, "evidence_event_ids": ["e000011"]},
                        cutoff="e000010", allowed_event_ids={"e000010"})
        with self.assertRaises(ValueError):
            validate_m1({**base, "rationale": "x" * 401},
                        cutoff="e000010", allowed_event_ids={"e000010"})

    def test_receipt_preserves_raw_response_and_model_identity(self):
        def fake(request):
            body = {"id": "v8-fake-response", "model": "Qwen/Qwen3-8B-FP8",
                    "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
            return {"status": 200, "body": json.dumps(body).encode(),
                    "model": "Qwen/Qwen3-8B-FP8",
                    "revision": "220b46e3b2180893580a4454f21f22d3ebb187d3",
                    "vllm_version": "0.10.2"}
        with tempfile.TemporaryDirectory() as temporary:
            transport = V8Transport(fake, Path(temporary), max_calls=1)
            parsed = transport.respond("B", {"messages": [{"role": "user", "content": "test"}],
                                            "tools": R_WORKER_TOOLS}, seed=17, kind="worker")
            self.assertEqual(parsed, {"final": "done"})
            receipt = json.loads((Path(temporary) / "00001_B/receipt.json").read_text())
            self.assertEqual(receipt["response_id"], "v8-fake-response")
            self.assertEqual(transport.usage["total_tokens"], 2)
            with self.assertRaises(RuntimeError):
                transport.respond("B", {"messages": [], "tools": R_WORKER_TOOLS},
                                  seed=17, kind="worker")


if __name__ == "__main__":
    unittest.main()
