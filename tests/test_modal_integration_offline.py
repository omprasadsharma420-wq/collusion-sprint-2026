"""No Modal app is started by these transport and abort-path tests."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_adapter_v3 import AgentAdapterV3
from modal_transport import (MODEL_NAME, MODEL_REVISION, VLLM_VERSION, ModalTransport,
                             build_completion_request, parse_completion_response)
from protocol_v3 import AGENTS, MEMO_MARKER, TOOL_SCHEMAS, CellConfig, prompt_sha256
from run_real_modal import run_cell, write_overview
from world_v3 import WorldV3, canonical


def completion(tool: str = "list_tickets", args: dict | None = None) -> bytes:
    return canonical({"id": "chatcmpl-offline", "model": "Qwen/Qwen3-8B-FP8",
                      "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                      "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant",
                          "tool_calls": [{"id": "call-offline", "type": "function",
                                          "function": {"name": tool,
                                                       "arguments": json.dumps(args or {})}}]}}]})


class ModalPlumbingTests(unittest.TestCase):
    def test_exact_schemas_and_decoding_are_fixed(self) -> None:
        raw = build_completion_request(canonical({"messages": [{"role": "user", "content": "diagnostic"}],
                                                  "tools": TOOL_SCHEMAS}))
        request = json.loads(raw)
        self.assertEqual(request["tools"], TOOL_SCHEMAS)
        self.assertEqual(len(request["tools"]), 12)
        self.assertEqual(request["temperature"], 0)
        self.assertFalse(request["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(request["max_tokens"], 768)
        self.assertEqual(request["tool_choice"], "auto")

    def test_tool_call_id_and_raw_response_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            body = completion()
            remote = lambda payload: {"status": 200, "body": body, "elapsed_seconds": 0.01,
                                      "model": MODEL_NAME, "revision": MODEL_REVISION,
                                      "vllm_version": VLLM_VERSION}
            transport = ModalTransport(remote, Path(temp))
            world = WorldV3("C", run_id="offline-id-test")
            adapter = AgentAdapterV3(world, transport, max_model_responses=1)
            status, result = adapter.step("A")
            self.assertEqual(status, "tool")
            self.assertTrue(result["ok"])
            self.assertEqual(adapter.messages["A"][-1]["tool_call_id"], "call-offline")
            self.assertEqual((Path(temp) / "0001_A" / "response.json").read_bytes(), body)
            self.assertEqual(transport.token_usage["total_tokens"], 14)

    def test_non_200_and_malformed_are_recorded_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            calls: list[bytes] = []
            def bad(payload: bytes) -> dict:
                calls.append(payload)
                return {"status": 400, "body": b'{"error":"bad request"}'}
            transport = ModalTransport(bad, Path(temp))
            request = canonical({"messages": [], "tools": TOOL_SCHEMAS})
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                transport.respond("A", request)
            self.assertEqual(len(calls), 1)
            self.assertEqual(transport.call_count, 1)
            self.assertTrue((Path(temp) / "0001_A" / "response.json").exists())
            receipt = json.loads((Path(temp) / "0001_A" / "receipt.json").read_text())
            self.assertEqual(receipt["status"], 400)
            with self.assertRaisesRegex(ValueError, "truncated"):
                parse_completion_response(canonical({"choices": [{"finish_reason": "length", "message": {"content": ""}}]}))

    def test_private_histories_and_cell_orthogonality(self) -> None:
        for cell in "ABCD":
            config = CellConfig.for_cell(cell)
            self.assertEqual(config.gate_known_direct, cell in "CD")
            self.assertEqual(config.reporting_reminder, cell in "BD")
            self.assertEqual(len({prompt_sha256(actor, config) for actor in AGENTS}), 4)
            world = WorldV3(cell, run_id=f"offline-isolation-{cell}")
            adapter = AgentAdapterV3(world, object())
            for actor in "BCD":
                self.assertNotIn(MEMO_MARKER, canonical(adapter.messages[actor]).decode())
            self.assertIn(MEMO_MARKER, canonical(adapter.messages["A"]).decode())

    def test_abort_exports_partial_real_records_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            class FailingTransport:
                call_count = 0
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                def respond(self, actor: str, serialized_request: bytes) -> dict:
                    self.call_count += 1
                    raise RuntimeError("offline injected provider failure")
            transport = FailingTransport()
            record = run_cell("C", root, transport, commit="offline-test", total_started=time.monotonic())
            self.assertEqual(record["status"], "ABORTED")
            self.assertEqual(record["model_calls"], 1)
            self.assertTrue((root / "C" / "trusted" / "events_v2.jsonl").exists())
            self.assertTrue((root / "C" / "researcher" / "replay.html").exists())
            self.assertTrue((root / "C" / "auditor" / "projections" / "pooled_metadata.jsonl").exists())
            write_overview(root, [record], smoke_result={"pass": True, "calls": 1})
            self.assertTrue((root / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
