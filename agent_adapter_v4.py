"""V4 agent loop: same scheduling and message semantics, v4 tool definitions."""

from __future__ import annotations

from agent_adapter_v3 import AgentAdapterV3
from protocol_v3 import AGENTS, first_user_text, system_text


class AgentAdapterV4(AgentAdapterV3):
    def __init__(self, world, transport, *, max_model_responses: int = 16) -> None:
        super().__init__(world, transport, max_model_responses=max_model_responses)
        self.messages = {
            actor: [{"role": "system", "content": system_text(actor, world.config)},
                    {"role": "user", "content": first_user_text(actor)}]
            for actor in AGENTS
        }
