"""Four private V7 agent histories; model choices are never scripted here."""

from __future__ import annotations

import copy
import json
from typing import Any

from protocol_v3 import AGENTS
from protocol_v7 import first_user_text, system_text
from agent_adapter_v3 import AgentAdapterV3


class AgentAdapterV7(AgentAdapterV3):
    def __init__(self, world, transport, *, max_model_responses: int = 24) -> None:
        super().__init__(world, transport, max_model_responses=max_model_responses)
        self.messages = {actor: [
            {"role": "system", "content": system_text(actor, world.config)},
            {"role": "user", "content": first_user_text(actor)},
        ] for actor in AGENTS}

    def step(self, actor: str) -> tuple[str, dict[str, Any] | None]:
        if actor not in AGENTS or self.finished[actor]:
            raise ValueError("Unknown or finished actor")
        if self.response_counts[actor] >= self.max_model_responses:
            raise RuntimeError("Fixed per-agent response cap exceeded")
        request = self.world.capture_model_input(actor, self.messages[actor])
        self.response_counts[actor] += 1
        try:
            response = copy.deepcopy(self.transport.respond(actor, request))
        except Exception as exc:
            self.world.capture_model_output(actor, {"transport_error": f"{type(exc).__name__}: {exc}"})
            raise
        self.world.capture_model_output(actor, response)
        if set(response) in ({"invalid_tool_call"}, {"invalid_model_output"}):
            self.finished[actor] = True
            return "model_invalid_output", None
        if set(response) == {"final"}:
            if not isinstance(response["final"], str):
                raise ValueError("Final response is not text")
            self.messages[actor].append({"role": "assistant", "content": response["final"]})
            self.finished[actor] = True
            return "final", None
        if set(response) != {"tool_call"}:
            raise ValueError("Malformed parsed provider response")
        call = response["tool_call"]
        if (not isinstance(call, dict) or set(call) != {"name", "arguments", "id"}
                or not isinstance(call["name"], str) or not isinstance(call["arguments"], dict)
                or not isinstance(call["id"], str)):
            raise ValueError("Malformed parsed tool call")
        self.messages[actor].append({"role": "assistant", "content": "", "tool_calls": [{
            "id": call["id"], "type": "function", "function": {
                "name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False,
                                                       separators=(",", ":"))}}]})
        result = self.world.execute_tool(actor, call["name"], call["arguments"])
        self.messages[actor].append({"role": "tool", "name": call["name"],
                                     "content": json.dumps(result, ensure_ascii=False, sort_keys=True),
                                     "tool_call_id": call["id"]})
        return "tool", result
