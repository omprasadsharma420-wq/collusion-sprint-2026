"""V4 task-usability interface layered on the frozen v3 world and verifier."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from protocol_v3 import AGENTS, ANSWER_KEYS
from protocol_v4 import FIELD_GUIDES, PROTOCOL_VERSION, TOOL_SCHEMAS, prompt_sha256, tool_schema_sha256
from world_v3 import WorldV3, canonical, normalize_findings, sha256


def eligible_tickets(world: WorldV3, actor: str) -> list[str]:
    if actor in world.owner_ticket:
        return []
    return [ticket for ticket in ("T1", "T2", "T3", "T4")
            if ticket not in world.owners and not (actor == "B" and ticket == "T4")]


class WorldV4(WorldV3):
    @staticmethod
    def _schema(tool_name: str) -> dict[str, Any]:
        for item in TOOL_SCHEMAS:
            if item["function"]["name"] == tool_name:
                return item["function"]["parameters"]
        raise ValueError("Unknown agent tool")

    def _handle(self, actor: str, name: str, args: dict[str, Any],
                tool_event_id: str) -> dict[str, Any]:
        if name == "assign_ticket":
            ticket = args["ticket_id"]
            if actor in self.owner_ticket:
                return {"ok": False, "status": "rejected",
                        "reason_code": "already_owns_ticket",
                        "existing_ticket_id": self.owner_ticket[actor],
                        "policy": "one_ticket_per_worker",
                        "eligible_ticket_ids": []}
            if ticket in self.owners:
                return {"ok": False, "status": "rejected",
                        "reason_code": "ticket_already_claimed", "ticket_id": ticket,
                        "current_owner": self.owners[ticket],
                        "eligible_ticket_ids": eligible_tickets(self, actor)}
            if actor == "B" and ticket == "T4":
                return {"ok": False, "status": "rejected",
                        "reason_code": "ticket_not_eligible_for_reviewer",
                        "ticket_id": ticket,
                        "eligible_ticket_ids": eligible_tickets(self, actor)}
            return super()._handle(actor, name, args, tool_event_id)
        if name == "read_ticket_artifact":
            result = super()._handle(actor, name, args, tool_event_id)
            result["submission_schema"] = copy.deepcopy(FIELD_GUIDES[args["ticket_id"]])
            return result
        if name == "submit_work":
            result = super()._handle(actor, name, args, tool_event_id)
            if result["ok"]:
                result["reason_code"] = "accepted"
                result["accepted_evidence_id"] = result["evidence_event_id"]
                return result
            ticket = args["ticket_id"]
            public_keys = set(FIELD_GUIDES[ticket])
            try:
                normalized, _ = normalize_findings(args["findings"])
            except ValueError:
                normalized = {
                    " ".join(item["key"].split()).casefold(): item["value"]
                    for item in args["findings"] if item.get("key")
                }
                result["reason_code"] = "structural_mismatch"
                result["format_constraints"] = copy.deepcopy(FIELD_GUIDES[ticket])
                result["missing_keys"] = sorted(public_keys - set(normalized))
                result["unexpected_keys"] = sorted(set(normalized) - public_keys)
                result["duplicate_or_empty_key"] = True
                return result
            missing = public_keys - set(normalized)
            unexpected = set(normalized) - public_keys
            if missing or unexpected:
                result["reason_code"] = "structural_mismatch"
                result["missing_keys"] = sorted(missing)
                result["unexpected_keys"] = sorted(unexpected)
                result["format_constraints"] = copy.deepcopy(FIELD_GUIDES[ticket])
            else:
                # The names are public. The hidden expected values never leave
                # the verifier; only names of mismatched fields are returned.
                result["reason_code"] = "value_mismatch"
                result["value_mismatch_keys"] = sorted(
                    key for key in public_keys
                    if normalized[key] != ANSWER_KEYS[ticket][key].casefold())
            return result
        return super()._handle(actor, name, args, tool_event_id)

    def capture_model_input(self, actor: str, messages: list[dict[str, Any]]) -> bytes:
        if actor not in AGENTS:
            raise ValueError("Unknown agent")
        request = {"messages": copy.deepcopy(messages), "tools": TOOL_SCHEMAS}
        raw = canonical(request)
        input_ref = f"model_inputs/{len(self.input_bytes) + 1:04d}.json"
        self.input_bytes.append(raw)
        self.trace.append("model_input_captured", actor, input_ref=input_ref,
                          input_sha256=sha256(raw))
        visible = self._visible_messages(messages)
        for message_id in sorted(self.pending_reads[actor]):
            stored = self.messages[message_id]
            if visible.get(message_id) != stored["body"]:
                continue
            delivery = self.delivery_event_ids[(message_id, actor)]
            self.trace.append("recipient_observation", actor, parents=(delivery,),
                              message_id=message_id, recipient=actor,
                              model_input_ref=input_ref,
                              payload_digest=stored["payload_digest"])
            self.observed_messages[actor].add(message_id)
        self.pending_reads[actor] -= self.observed_messages[actor]
        for message in messages:
            if message.get("role") != "tool":
                continue
            try:
                result = json.loads(message["content"])
            except (json.JSONDecodeError, KeyError):
                continue
            ticket = result.get("ticket_id")
            from protocol_v3 import ARTIFACTS
            if ticket in ARTIFACTS and result.get("artifact") == ARTIFACTS[ticket]:
                self.seen_artifacts[actor].add(ticket)
        return raw

    def export(self, root: Path, *, source_commit: str | None = None) -> None:
        super().export(root, source_commit=source_commit)
        path = root / "trusted" / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["protocol_version"] = PROTOCOL_VERSION
        manifest["prompt_sha256"] = {
            actor: prompt_sha256(actor, self.config) for actor in AGENTS}
        manifest["tool_schema_sha256"] = tool_schema_sha256()
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
