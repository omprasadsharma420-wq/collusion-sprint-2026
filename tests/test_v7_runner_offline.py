"""Pure fake-wire checks of V7 runner persistence; no real provider import/call."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from modal_transport_v7 import BLOCK_SEEDS, ModalTransportV7
from run_real_modal_v7 import (MAX_GPU_WALL_SECONDS, MAX_STUDY_CALLS,
                               SCHEDULE, run_episode, write_overview)


class V7RunnerOfflineTests(unittest.TestCase):
    def test_fixed_balanced_schedule_caps_and_no_outcome_gate(self):
        self.assertEqual(SCHEDULE, ((1, "C"), (1, "A"), (1, "D"), (1, "B"),
                                    (2, "B"), (2, "D"), (2, "A"), (2, "C")))
        self.assertEqual(MAX_STUDY_CALLS, 768)
        self.assertEqual(MAX_GPU_WALL_SECONDS, 10800)

    def test_noop_real_wire_shape_episode_validates_and_stays_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            counter = 0
            def remote(request):
                nonlocal counter
                counter += 1
                body = json.dumps({"id": f"fake-wire-{counter}", "model": "Qwen/Qwen3-8B-FP8",
                                   "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
                                   "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                             "total_tokens": 2}}).encode()
                return {"status": 200, "body": body, "model": "Qwen/Qwen3-8B-FP8",
                        "revision": "220b46e3b2180893580a4454f21f22d3ebb187d3",
                        "vllm_version": "0.10.2"}
            transport = ModalTransportV7(remote, root / "trusted_provider_calls",
                                         seed=BLOCK_SEEDS[1], max_calls=768)
            record, validation = run_episode("01_C", 1, "C", root, transport,
                                             source_commit="SOFTWARE_CONTROL", total_started=time.monotonic())
            self.assertEqual(record["model_calls"], 4)
            self.assertEqual(record["outcome"]["task_score"], 0)
            self.assertEqual(record["status"], "ALL_FINAL")
            self.assertTrue(validation["validation_ok"], validation)
            write_overview(root, [record])
            overview = json.loads((root / "V7_REAL_RESULTS.json").read_text())
            self.assertEqual(len(overview["episodes"]), 8)
            self.assertEqual(overview["episodes"][0]["task_score"], 0)
            self.assertEqual(overview["episodes"][1]["status"], "PLANNED_NOT_RUN")


if __name__ == "__main__":
    unittest.main()
