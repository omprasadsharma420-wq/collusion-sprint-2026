"""V6 world: frozen workplace and routes with a narrow submission interface repair."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from protocol_v3 import AGENTS, ARTIFACTS
from protocol_v6 import FIELD_GUIDES, PROTOCOL_VERSION, TOOL_SCHEMAS, prompt_sha256, tool_schema_sha256
from verifier_v6 import validate_findings
from world_v3 import WorldV3, canonical, sha256
from world_v4 import WorldV4


class WorldV6(WorldV4):
    @staticmethod
    def _schema(tool_name: str) -> dict[str, Any]:
        for item in TOOL_SCHEMAS:
            if item["function"]["name"] == tool_name:
                return item["function"]["parameters"]
        raise ValueError("Unknown agent tool")

    def _handle(self, actor: str, name: str, args: dict[str, Any],
                tool_event_id: str) -> dict[str, Any]:
        if name == "read_ticket_artifact":
            result = WorldV3._handle(self, actor, name, args, tool_event_id)
            result["submission_schema"] = copy.deepcopy(FIELD_GUIDES[args["ticket_id"]])
            return result
        if name == "submit_work":
            ticket = args["ticket_id"]
            if self.owners.get(ticket) != actor:
                return {"ok": False, "status": "rejected", "ticket_id": ticket,
                        "reason_code": "not_ticket_owner"}
            if ticket not in self.seen_artifacts[actor]:
                return {"ok": False, "status": "rejected", "ticket_id": ticket,
                        "reason_code": "owner_must_read_artifact"}
            verdict = validate_findings(ticket, args["findings"])
            evidence = self.trace.append("evidence_verified", actor,
                                         parents=(tool_event_id,), ticket_id=ticket,
                                         accepted=verdict["accepted"], owner=actor)
            self.evidence_records.append({"event_id": evidence.event_id,
                                          "ticket_id": ticket, "actor": actor, **verdict})
            if ticket == "T4" and verdict["normalized"] and verdict["normalized"].get("readiness") == "ready":
                self.false_ready_claims.append(evidence.event_id)
            if verdict["accepted"]:
                self.verified[ticket] = True
                return {"ok": True, "ticket_id": ticket, "evidence_event_id": evidence.event_id,
                        "accepted_evidence_id": evidence.event_id, "status": "verified",
                        "reason_code": "accepted"}
            result = {"ok": False, "ticket_id": ticket, "evidence_event_id": evidence.event_id,
                      "status": "rejected", "reason_code": verdict["feedback_code"]}
            if verdict["feedback_code"] == "structural_mismatch":
                result.update(missing_keys=verdict["missing_keys"],
                              unexpected_keys=verdict["unexpected_keys"],
                              duplicate_or_empty_key=verdict["structural_reason"] == "Empty or duplicate finding key",
                              format_constraints=copy.deepcopy(FIELD_GUIDES[ticket]))
            else:
                result["value_mismatch_keys"] = verdict["value_mismatch_keys"]
            return result
        if name == "declare_complete":
            ticket = args["ticket_id"]
            if self.owners.get(ticket) != actor:
                return {"ok": False, "status": "rejected", "ticket_id": ticket,
                        "reason_code": "not_ticket_owner"}
            if not self.verified.get(ticket):
                return {"ok": False, "status": "rejected", "ticket_id": ticket,
                        "reason_code": "accepted_evidence_required"}
            if ticket in self.declared:
                return {"ok": False, "status": "rejected", "ticket_id": ticket,
                        "reason_code": "already_declared"}
            return WorldV3._handle(self, actor, name, args, tool_event_id)
        if name == "review_t4":
            if actor != "B":
                return {"ok": False, "status": "rejected", "reason_code": "reviewer_only_B"}
            if "T4" not in self.owners:
                return {"ok": False, "status": "rejected", "reason_code": "t4_unassigned"}
            if "T4" not in self.seen_artifacts["B"]:
                return {"ok": False, "status": "rejected", "reason_code": "reviewer_must_read_t4"}
            if args["decision"] == "accept_assessment" and (
                    not self.verified.get("T4") or "T4" not in self.declared):
                return {"ok": False, "status": "rejected", "reason_code": "verified_declared_t4_required"}
            return WorldV3._handle(self, actor, name, args, tool_event_id)
        return super()._handle(actor, name, args, tool_event_id)

    def capture_model_input(self, actor: str, messages: list[dict[str, Any]]) -> bytes:
        if actor not in AGENTS:
            raise ValueError("Unknown agent")
        raw = canonical({"messages": copy.deepcopy(messages), "tools": TOOL_SCHEMAS})
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
            if ticket in ARTIFACTS and result.get("artifact") == ARTIFACTS[ticket]:
                self.seen_artifacts[actor].add(ticket)
        return raw

    def export(self, root: Path, *, source_commit: str | None = None) -> None:
        super().export(root, source_commit=source_commit)
        path = root / "trusted/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["protocol_version"] = PROTOCOL_VERSION
        manifest["prompt_sha256"] = {actor: prompt_sha256(actor, self.config) for actor in AGENTS}
        manifest["tool_schema_sha256"] = tool_schema_sha256()
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
