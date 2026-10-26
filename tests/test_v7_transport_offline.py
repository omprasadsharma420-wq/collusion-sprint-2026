"""No-cost exact-wire and malformed-model-output checks for V7."""

import json
import tempfile
import unittest
from pathlib import Path

from agent_adapter_v7 import AgentAdapterV7
from modal_transport_v7 import (BLOCK_SEEDS, MAX_GENERATION_TOKENS, TEMPERATURE,
                                ModalTransportV7, completion_request, parse_response)
from protocol_v7 import TOOL_SCHEMAS
from world_v7 import WorldV7


def provider_body(*, args='{"ticket_id":"T1","findings":{}}', name="submit_work"):
    return json.dumps({"id": "chatcmpl-software-fixture", "model": "Qwen/Qwen3-8B-FP8",
                       "choices": [{"finish_reason": "tool_calls", "message": {
                           "tool_calls": [{"id": "call-fixture", "type": "function",
                                           "function": {"name": name, "arguments": args}}]}}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()


class V7TransportOfflineTests(unittest.TestCase):
    def test_exact_request_sampling_schema_and_seed(self):
        request = completion_request(json.dumps({"messages": [{"role": "user", "content": "SMOKE_NOT_DATA"}],
                                                 "tools": TOOL_SCHEMAS}).encode(), seed=BLOCK_SEEDS[1])
        payload = json.loads(request)
        self.assertEqual(payload["temperature"], TEMPERATURE)
        self.assertEqual(payload["max_tokens"], MAX_GENERATION_TOKENS)
        self.assertEqual(payload["seed"], 20261026)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["parallel_tool_calls"], False)
        self.assertEqual(payload["tools"], TOOL_SCHEMAS)

    def test_model_generated_invalid_json_preserved_not_repaired(self):
        parsed, _ = parse_response(provider_body(args="{not json"))
        self.assertEqual(set(parsed), {"invalid_tool_call"})
        self.assertEqual(parsed["invalid_tool_call"]["raw_arguments"], "{not json")

    def test_valid_flat_submit_parse_and_identity_receipt(self):
        parsed, metadata = parse_response(provider_body())
        self.assertEqual(parsed["tool_call"]["name"], "submit_work")
        self.assertEqual(parsed["tool_call"]["arguments"]["ticket_id"], "T1")
        with tempfile.TemporaryDirectory() as folder:
            def remote(request):
                return {"status": 200, "body": provider_body(),
                        "model": "Qwen/Qwen3-8B-FP8",
                        "revision": "220b46e3b2180893580a4454f21f22d3ebb187d3",
                        "vllm_version": "0.10.2"}
            transport = ModalTransportV7(remote, Path(folder), seed=BLOCK_SEEDS[1], max_calls=1)
            world = WorldV7("A", run_id="v7-offline-transport")
            adapter = AgentAdapterV7(world, transport)
            status, result = adapter.step("A")
            self.assertEqual(status, "tool")
            self.assertFalse(result["ok"])
            receipt = json.loads((Path(folder) / "0001_A" / "receipt.json").read_text())
            self.assertEqual(receipt["response_id"], metadata["response_id"])
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(len(world.input_bytes), len(world.output_bytes))

    def test_invalid_model_tool_call_finishes_actor_without_world_action(self):
        with tempfile.TemporaryDirectory() as folder:
            def remote(request):
                return {"status": 200, "body": provider_body(args="{bad"),
                        "model": "Qwen/Qwen3-8B-FP8",
                        "revision": "220b46e3b2180893580a4454f21f22d3ebb187d3",
                        "vllm_version": "0.10.2"}
            adapter = AgentAdapterV7(WorldV7("A", run_id="v7-invalid-model"),
                                     ModalTransportV7(remote, Path(folder), seed=20261026, max_calls=1))
            status, result = adapter.step("A")
            self.assertEqual(status, "model_invalid_output")
            self.assertIsNone(result)
            self.assertTrue(adapter.finished["A"])
            self.assertEqual(adapter.world.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
