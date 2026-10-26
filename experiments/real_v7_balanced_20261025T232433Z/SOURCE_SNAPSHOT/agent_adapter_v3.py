"""Provider-agnostic offline agent loop; an injected transport owns all responses."""

from __future__ import annotations

import copy
import json
from typing import Any, Protocol

from protocol_v3 import AGENTS, TOOL_SCHEMAS, first_user_text, system_text
from world_v3 import WorldV3


class ModelTransport(Protocol):
    def respond(self, actor: str, serialized_request: bytes) -> dict[str, Any]: ...


class AgentAdapterV3:
    def __init__(self, world: WorldV3, transport: ModelTransport,
                 *, max_model_responses: int | None = None) -> None:
        self.world = world
        self.transport = transport
        self.max_model_responses = max_model_responses or world.tool_call_cap + 1
        self.response_counts = {actor: 0 for actor in AGENTS}
        self.finished = {actor: False for actor in AGENTS}
        self.messages: dict[str, list[dict[str, Any]]] = {
            actor: [{"role": "system", "content": system_text(actor, world.config)},
                    {"role": "user", "content": first_user_text(actor)}]
            for actor in AGENTS
        }

    def step(self, actor: str) -> tuple[str, dict[str, Any] | None]:
        if actor not in AGENTS:
            raise ValueError("Unknown agent")
        if self.finished[actor]:
            return "already_finished", None
        if self.response_counts[actor] >= self.max_model_responses:
            raise RuntimeError("Fixed per-agent model-response cap exceeded")
        request = self.world.capture_model_input(actor, self.messages[actor])
        self.response_counts[actor] += 1
        try:
            response = copy.deepcopy(self.transport.respond(actor, request))
        except Exception as exc:
            self.world.capture_model_output(actor, {"transport_error": f"{type(exc).__name__}: {exc}"})
            raise
        if not isinstance(response, dict):
            raise ValueError("Transport response must be an object")
        self.world.capture_model_output(actor, response)
        if set(response) not in ({"tool_call"}, {"final"}):
            raise ValueError("Transport response must be one tool_call or one final")
        if "final" in response:
            if not isinstance(response["final"], str):
                raise ValueError("Final response must be text")
            self.messages[actor].append({"role": "assistant", "content": response["final"]})
            self.finished[actor] = True
            return "final", None
        call = response["tool_call"]
        if not isinstance(call, dict) or set(call) not in ({"name", "arguments"}, {"name", "arguments", "id"}):
            raise ValueError("Tool call needs name and arguments")
        name, arguments = call["name"], call["arguments"]
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ValueError("Invalid tool call argument types")
        if "id" in call:
            call_id = call["id"]
            if not isinstance(call_id, str) or not call_id:
                raise ValueError("Invalid model tool-call ID")
            self.messages[actor].append({"role": "assistant", "content": "", "tool_calls": [{
                "id": call_id, "type": "function", "function": {
                    "name": name, "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))}}]})
        else:
            self.messages[actor].append({"role": "assistant", "content": "", "tool_call": copy.deepcopy(call)})
        result = self.world.execute_tool(actor, name, arguments)
        tool_message: dict[str, Any] = {"role": "tool", "name": name,
                                        "content": json.dumps(result, ensure_ascii=False, sort_keys=True)}
        if "id" in call:
            tool_message["tool_call_id"] = call["id"]
        self.messages[actor].append(tool_message)
        return "tool", result

    def run_actor(self, actor: str) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        while not self.finished[actor]:
            status, result = self.step(actor)
            if status == "tool" and result is not None:
                outputs.append(result)
        return outputs


class CannedMockTransport:
    """Fixed software plumbing stimulus. Its choices are not model behavior."""

    def __init__(self, plans: dict[str, list[tuple[str, dict[str, Any]]]]) -> None:
        self.plans = {actor: list(plan) for actor, plan in plans.items()}
        self.index = {actor: 0 for actor in AGENTS}
        self.requests: list[tuple[str, bytes]] = []

    def respond(self, actor: str, serialized_request: bytes) -> dict[str, Any]:
        # Reading the exact request proves injection without any hosted provider.
        request = json.loads(serialized_request)
        if len(request["tools"]) != len(TOOL_SCHEMAS):
            raise ValueError("Unexpected tool list")
        self.requests.append((actor, serialized_request))
        position = self.index[actor]
        self.index[actor] += 1
        if position >= len(self.plans.get(actor, [])):
            return {"final": "Mock transport finished its predetermined actions."}
        name, arguments = self.plans[actor][position]
        return {"tool_call": {"name": name, "arguments": copy.deepcopy(arguments)}}
