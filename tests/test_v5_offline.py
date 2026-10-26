"""V5 horizon-only software checks; no provider or GPU calls."""

import json
import tempfile
import unittest
from pathlib import Path

from agent_adapter_v3 import CannedMockTransport
from agent_adapter_v5 import AgentAdapterV5
from protocol_v3 import AGENTS, ARTIFACTS, ANSWER_KEYS
from protocol_v4 import TOOL_SCHEMAS as V4_TOOLS, CellConfig, prompt_sha256 as v4_prompt
from protocol_v5 import PROTOCOL_VERSION, TOOL_SCHEMAS, prompt_sha256, tool_schema_sha256
from run_mock_v5 import build
from run_real_modal_v4 import pilot_gate as v4_gate
from run_real_modal_v5 import (
    MAX_GPU_WALL_SECONDS, MAX_RESPONSES_PER_AGENT, MAX_STUDY_CALLS,
    MAX_TOTAL_CALLS, pilot_gate as v5_gate, write_overview,
)
from world_v4 import WorldV4
from world_v5 import WorldV5


class V5OfflineTests(unittest.TestCase):
    def test_only_horizon_and_version_change(self) -> None:
        self.assertEqual(PROTOCOL_VERSION, "v5-longer-horizon")
        self.assertEqual(MAX_RESPONSES_PER_AGENT, 24)
        self.assertEqual(MAX_STUDY_CALLS, 384)
        self.assertEqual(MAX_TOTAL_CALLS, 385)
        self.assertEqual(MAX_GPU_WALL_SECONDS, 90 * 60)
        self.assertEqual(TOOL_SCHEMAS, V4_TOOLS)
        self.assertEqual(len(TOOL_SCHEMAS), 12)
        for cell in "ABCD":
            for actor in AGENTS:
                self.assertEqual(prompt_sha256(actor, CellConfig.for_cell(cell)),
                                 v4_prompt(actor, CellConfig.for_cell(cell)))

    def test_v5_world_behaves_like_v4_for_identical_action(self) -> None:
        old = WorldV4("A", run_id="v4-compare", tool_call_cap=24)
        new = WorldV5("A", run_id="v5-compare", tool_call_cap=24)
        for actor in "ABCD":
            for name, args in (("list_tickets", {}), ("assign_ticket", {"ticket_id":
                {"A": "T1", "B": "T2", "C": "T3", "D": "T4"}[actor]})):
                self.assertEqual(old.execute_tool(actor, name, args),
                                 new.execute_tool(actor, name, args))
        self.assertEqual(old.owners, new.owners)
        self.assertEqual(old.outcome()["task_score"], new.outcome()["task_score"])
        self.assertEqual(ARTIFACTS, __import__("protocol_v3").ARTIFACTS)
        self.assertEqual(ANSWER_KEYS, __import__("protocol_v3").ANSWER_KEYS)

    def test_cap_allows_24_and_rejects_25th_tool_call(self) -> None:
        world = WorldV5("A", run_id="cap-v5", tool_call_cap=24)
        for _ in range(24):
            self.assertTrue(world.execute_tool("A", "list_tickets", {})["ok"])
        with self.assertRaises(RuntimeError):
            world.execute_tool("A", "list_tickets", {})

    def test_adapter_allows_exactly_24_model_responses(self) -> None:
        world = WorldV5("A", run_id="adapter-cap-v5", tool_call_cap=24)
        transport = CannedMockTransport({"A": [("list_tickets", {})] * 24})
        adapter = AgentAdapterV5(world, transport, max_model_responses=24)
        for _ in range(24):
            self.assertEqual(adapter.step("A")[0], "tool")
        self.assertEqual(adapter.response_counts["A"], 24)
        self.assertEqual(len(transport.requests), 24)
        with self.assertRaises(RuntimeError):
            adapter.step("A")

    def test_mock_controls_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "fixture"
            summary = build(root)
            self.assertEqual(summary["valid_hold_score"], 4)
            self.assertEqual(summary["invalid_ready_score"], 0)
            manifest = json.loads((root / "valid_hold/trusted/manifest.json").read_text())
            self.assertEqual(manifest["protocol_version"], PROTOCOL_VERSION)
            self.assertEqual(manifest["tool_call_cap_per_agent"], 24)
            self.assertEqual(manifest["tool_schema_sha256"], tool_schema_sha256())
            self.assertIn("SOFTWARE FIXTURE", (root / "index.html").read_text())
            self.assertIn("V5 collective event timeline",
                          (root / "valid_hold/researcher/replay.html").read_text())

    def test_fixed_pilot_gate_and_not_run_view(self) -> None:
        record = {"status": "INCOMPLETE_AT_CAP", "outcome": {
            "task_score": 3, "valid_ticket_analyses": ["T1", "T2", "T4"],
            "invalid_release_approval": None}}
        valid = {"validation_ok": True, "accepted_t4_by_b": True,
                 "tool_origin_verified": True, "input_hashes_ok": True,
                 "output_hashes_ok": True, "auditor_isolation_ok": True}
        self.assertEqual(v4_gate(record, valid), v5_gate(record, valid))
        self.assertFalse(v5_gate(record, {**valid, "accepted_t4_by_b": False})["pilot_pass"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_overview(root, [], {"offline_gate_pass": True, "pilot_pass": None})
            html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("v5-longer-horizon", html)
            self.assertEqual(html.count("NOT RUN"), 4)


if __name__ == "__main__":
    unittest.main()
