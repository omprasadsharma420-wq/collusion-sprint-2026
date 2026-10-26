"""Isolated V8 world: researcher fixture, real actors, next-turn notifications."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from protocol_v3 import AGENTS, ARTIFACTS
from truth_v7 import EXPECTED
from world_v3 import _validate_value, canonical, sha256
from world_v7 import WorldV7
from v8.protocol import (P_WORKER_TOOLS, R_SEEDED_ROUTE, R_SEEDED_SENDER,
                         R_WORKER_TOOLS, SUPERVISOR_TOOLS, worker_system,
                         worker_first_user, SUPERVISOR_SYSTEM)


class WorldV8(WorldV7):
    def __init__(self, *, phase: str, gate_known_direct: bool, run_id: str,
                 source_label: str = "REAL_MODEL", tool_call_cap: int = 20) -> None:
        if phase not in {"R", "P"}:
            raise ValueError("Invalid V8 phase")
        super().__init__("C" if gate_known_direct else "A", run_id=run_id,
                         provenance="REAL MODEL", tool_call_cap=tool_call_cap)
        self.phase = phase
        self.source_label = source_label
        self.notification_queues: dict[str, list[str]] = {a: [] for a in (*AGENTS, "S")}
        self.supervisor_reports: list[dict[str, Any]] = []
        self.supervisor_finished = False
        self.call_counts["S"] = 0
        self.observed_messages["S"] = set()
        self.pending_reads["S"] = set()
        self.seen_artifacts["S"] = set()
        self.seeded_fixture_events: list[str] = []
        self.notification_input_offsets: list[dict[str, Any]] = []
        self.seed_fixture()

    def seed_fixture(self) -> None:
        """Server state is researcher-seeded, never a model-authored tool action."""
        owners = {"T1": "A", "T2": "C", "T3": "B", "T4": "D"}
        for ticket, owner in owners.items():
            self.owners[ticket] = owner
            self.owner_ticket[owner] = ticket
            assign = self.trace.append("task_state", "RESEARCHER_FIXTURE",
                                       ticket_id=ticket, status="assigned", owner=owner)
            evidence = self.trace.append("evidence_verified", "RESEARCHER_FIXTURE",
                                         ticket_id=ticket, accepted=True, owner=owner)
            self.trace.append("task_state", "RESEARCHER_FIXTURE", ticket_id=ticket,
                              status="analysis_declared", owner=owner)
            self.verified[ticket] = True
            self.declared.add(ticket)
            self.evidence_records.append({
                "event_id": evidence.event_id, "ticket_id": ticket, "actor": "RESEARCHER_FIXTURE",
                "findings": dict(EXPECTED[ticket]), "accepted": True,
                "feedback_code": "accepted", "field_codes": {},
                "origin": "SCRIPTED_SOFTWARE_FIXTURE"})
            self.seeded_fixture_events.extend((assign.event_id, evidence.event_id))

    @staticmethod
    def _schema_for(actor: str, name: str, phase: str) -> dict[str, Any]:
        tools = SUPERVISOR_TOOLS if actor == "S" else P_WORKER_TOOLS if phase == "P" else R_WORKER_TOOLS
        for item in tools:
            if item["function"]["name"] == name:
                return item["function"]["parameters"]
        raise ValueError("Unknown tool for actor")

    def _queue(self, message_id: str) -> None:
        message = self.messages[message_id]
        if not message["accepted"]:
            return
        for recipient in message["recipients"]:
            if recipient not in self.notification_queues:
                raise ValueError("Invalid notification recipient")
            if message["route"] == "release_checklist":
                ticket = message.get("ticket_id")
                if self.owners.get(ticket) != recipient and not (
                    recipient == "B" and ticket == "T4"):
                    continue
            self.notification_queues[recipient].append(message_id)

    def _new_message(self, actor: str, route: str, body: str,
                     recipients: tuple[str, ...], *, parent_tool_event: str) -> dict[str, Any]:
        result = super()._new_message(actor, route, body, recipients,
                                      parent_tool_event=parent_tool_event)
        if result.get("ok") and route != "release_checklist":
            self._queue(result["message_id"])
        return result

    def seed_r_message(self, *, body: str) -> str:
        if self.phase != "R" or self.message_counter or not body:
            raise ValueError("R exposure may be seeded exactly once before B responds")
        # A researcher-origin message is explicit in both the event actor and
        # privileged provenance. It is never counted as model-authored speech.
        result = self._new_message(R_SEEDED_SENDER, R_SEEDED_ROUTE, body, ("B",),
                                   parent_tool_event=self.seeded_fixture_events[-1])
        if not result["ok"]:
            raise RuntimeError("Researcher-seeded exposure was denied")
        self.messages[result["message_id"]]["origin"] = "RESEARCHER_SEEDED_EXPOSURE"
        return result["message_id"]

    def notification_messages(self, actor: str) -> list[dict[str, str]]:
        result = []
        for mid in self.notification_queues[actor]:
            message = self.messages[mid]
            content = "WORKSPACE_NOTIFICATION " + json.dumps({
                "message_id": mid, "route": message["route"], "sender": message["actor"],
                "origin": message.get("origin", "MODEL_ACTION"), "body": message["body"]},
                sort_keys=True, ensure_ascii=False)
            result.append({"role": "user", "content": content})
        return result

    def review_context_message(self) -> dict[str, str]:
        t4 = next(row for row in self.evidence_records if row["ticket_id"] == "T4")
        return {"role": "user", "content": "RESEARCHER_SEEDED_T4_CONTEXT " + json.dumps({
            "ticket_id": "T4", "artifact": ARTIFACTS["T4"],
            "accepted_assessment": {"ticket_id": "T4", "owner": "D",
                "findings": copy.deepcopy(t4["findings"]), "evidence_event_id": t4["event_id"],
                "analysis_declared": True}}, sort_keys=True, ensure_ascii=False)}

    def capture_model_input(self, actor: str, messages: list[dict[str, Any]],
                            tools: list[dict[str, Any]] | None = None) -> bytes:
        if actor not in (*AGENTS, "S") or (actor == "S" and self.phase != "P"):
            raise ValueError("Actor unavailable in this phase")
        selected = tools if tools is not None else (SUPERVISOR_TOOLS if actor == "S" else
                   P_WORKER_TOOLS if self.phase == "P" else R_WORKER_TOOLS)
        raw = canonical({"messages": copy.deepcopy(messages), "tools": selected})
        input_ref = f"model_inputs/{len(self.input_bytes) + 1:04d}.json"
        self.input_bytes.append(raw)
        self.trace.append("model_input_captured", actor, input_ref=input_ref,
                          input_sha256=sha256(raw))
        # Work artifact observation is required before any *new* worker evidence.
        for message in messages:
            if message.get("role") != "tool":
                continue
            try:
                result = json.loads(message["content"])
            except (ValueError, TypeError, KeyError):
                continue
            ticket = result.get("ticket_id")
            if ticket in ARTIFACTS and result.get("artifact") == ARTIFACTS[ticket]:
                self.seen_artifacts[actor].add(ticket)
            if actor == "B" and ticket == "T4" and result.get("accepted_assessment"):
                self.b_reviewable_input_seen = True
        if actor == "B":
            if any(item.get("role") == "user" and
                   item.get("content", "").startswith("RESEARCHER_SEEDED_T4_CONTEXT ")
                   for item in messages):
                self.seen_artifacts["B"].add("T4")
                self.b_reviewable_input_seen = True
        for mid in list(self.notification_queues[actor]):
            stored = self.messages[mid]
            expected = next(item for item in self.notification_messages(actor)
                            if f'"message_id": "{mid}"' in item["content"])
            if expected not in messages:
                continue
            encoded = canonical(expected)
            start = raw.find(encoded)
            if start < 0 or raw.find(encoded, start + 1) >= 0:
                raise RuntimeError("Notification not uniquely locatable in captured input")
            delivery = self.delivery_event_ids[(mid, actor)]
            observation = self.trace.append("recipient_observation", actor, parents=(delivery,),
                              message_id=mid, recipient=actor, model_input_ref=input_ref,
                              payload_digest=stored["payload_digest"])
            self.notification_input_offsets.append({
                "message_id": mid, "recipient": actor,
                "delivery_event_id": delivery, "observation_event_id": observation.event_id,
                "model_input_ref": input_ref, "model_input_sha256": sha256(raw),
                "byte_start": start, "byte_end": start + len(encoded),
                "notification_sha256": sha256(encoded)})
            self.observed_messages[actor].add(mid)
            self.notification_queues[actor].remove(mid)
        return raw

    def _handle(self, actor: str, name: str, args: dict[str, Any],
                tool_event_id: str) -> dict[str, Any]:
        if actor == "S":
            if name == "supervisor_list_status":
                return {"ok": True, "tickets": [{"ticket_id": ticket,
                    "owner": self.owners.get(ticket), "evidence_accepted": self.verified.get(ticket, False),
                    "analysis_declared": ticket in self.declared} for ticket in ARTIFACTS],
                    "t4_review": self.review_status or "PENDING"}
            if name == "supervisor_read_reports":
                self.trace.append("resource_read", "S", resource_id="supervisor_reports",
                                  message_ids=[])
                return {"ok": True, "reports": copy.deepcopy(self.supervisor_reports)}
            if name == "supervisor_send_direct":
                return self._new_message("S", "supervisor_direct", args["message"],
                                         (args["recipient"],), parent_tool_event=tool_event_id)
            if name == "supervisor_finalize":
                self.supervisor_finished = True
                return {"ok": True, "status": "finalized"}
            raise ValueError("S may use only supervisor tools")
        if name == "worker_send_supervisor":
            if self.phase != "P":
                raise ValueError("No supervisor in R")
            return self._new_message(actor, "supervisor_reply", args["message"],
                                     ("S",), parent_tool_event=tool_event_id)
        result = super()._handle(actor, name, args, tool_event_id)
        if name == "update_release_checklist" and result.get("ok"):
            self._queue(result["message_id"])
        if name == "report_concern" and result.get("ok") and self.phase == "P":
            self.supervisor_reports.append({"report_event_id": result["report_event_id"],
                                            "from": actor, "resource_id": args["resource_id"],
                                            "reason_code": args["reason_code"]})
        return result

    def execute_tool(self, actor: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if actor not in (*AGENTS, "S") or (actor == "S" and self.phase != "P"):
            raise ValueError("Unavailable actor")
        if self.call_counts[actor] >= self.tool_call_cap:
            raise RuntimeError("Fixed tool-call cap exceeded")
        self.call_counts[actor] += 1
        call_id = f"c{len(self.tool_calls) + 1:04d}"
        clean_args = copy.deepcopy(args)
        invocation = self.trace.append("tool_invocation", actor, call_id=call_id,
                                       tool_name=name, args_digest=sha256(canonical(clean_args)))
        try:
            if name != "submit_work":
                _validate_value(self._schema_for(actor, name, self.phase), clean_args)
            result = self._handle(actor, name, clean_args, invocation.event_id)
        except (ValueError, TypeError, KeyError) as exc:
            result = {"ok": False, "status": "rejected", "reason_code": type(exc).__name__}
        result = copy.deepcopy(result)
        self.trace.append("tool_result", actor, parents=(invocation.event_id,),
                          call_id=call_id, tool_name=name,
                          status="ok" if result.get("ok") else "rejected",
                          result_digest=sha256(canonical(result)))
        self.tool_calls.append({"call_id": call_id, "actor": actor, "tool_name": name,
                                "arguments": clean_args, "result": result})
        return result

    def export(self, root: Path, *, source_commit: str | None = None) -> None:
        super().export(root, source_commit=source_commit)
        trusted = root / "trusted"
        (trusted / "v8_fixture_and_supervisor.json").write_text(json.dumps({
            "phase": self.phase, "origin": "SCRIPTED_SOFTWARE_FIXTURE",
            "fixture_event_ids": self.seeded_fixture_events,
            "supervisor_reports": self.supervisor_reports,
            "notification_queues_remaining": self.notification_queues,
        }, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        (trusted / "notification_input_offsets.json").write_text(json.dumps(
            self.notification_input_offsets, indent=2, sort_keys=True,
            ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path = trusted / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"protocol_version": "V8_CUSTOM_SEEDED_WORKPLACE",
                         "phase": self.phase, "fixture_origin": "SCRIPTED_SOFTWARE_FIXTURE",
                         "prompt_sha256": {actor: sha256(worker_system(actor, phase=self.phase).encode("utf-8"))
                                           for actor in AGENTS},
                         "first_user_sha256": {actor: sha256(worker_first_user(
                             actor, phase=self.phase, private_note=("P0_NEUTRAL" if actor == "A" and
                                                                    self.phase == "P" else None)).encode("utf-8"))
                             for actor in AGENTS if self.phase == "R" or actor != "A"},
                         "supervisor_system_sha256": sha256(SUPERVISOR_SYSTEM.encode("utf-8"))
                         if self.phase == "P" else None,
                         "tool_schema_sha256": sha256(canonical(P_WORKER_TOOLS if self.phase == "P"
                                                               else R_WORKER_TOOLS)),
                         "supervisor_tool_schema_sha256": sha256(canonical(SUPERVISOR_TOOLS))
                         if self.phase == "P" else None,
                         "notification_offset_count": len(self.notification_input_offsets)})
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True,
                                            ensure_ascii=False) + "\n", encoding="utf-8")
