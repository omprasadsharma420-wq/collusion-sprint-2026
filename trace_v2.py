"""Versioned, software-only trace contract. This module does not run agents.

V1 fixture reads are deliberately *not* promoted to model-input observations.
Only an independently captured model_input_ref can support that v2 event.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from events import Event


SCHEMA_VERSION = 2
KINDS = frozenset({
    "attempt", "authorization_denial", "accepted_write", "recipient_delivery",
    "recipient_observation", "agent_discovery_report", "monitor_alert",
    "supervisor_decision", "legacy_event", "tool_invocation", "tool_result",
    "model_input_captured", "model_output_captured", "resource_read",
    "evidence_verified", "task_state",
})
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID = re.compile(r"^e[0-9]{6,}$")
_FIELDS: dict[str, frozenset[str]] = {
    "attempt": frozenset({"message_id", "route", "recipients", "payload_digest"}),
    "authorization_denial": frozenset({"message_id", "reason_code"}),
    "accepted_write": frozenset({"message_id", "resource_id"}),
    "recipient_delivery": frozenset({"message_id", "recipient"}),
    "recipient_observation": frozenset({"message_id", "recipient", "model_input_ref", "payload_digest"}),
    "agent_discovery_report": frozenset({"resource_id", "reason_code"}),
    "monitor_alert": frozenset({"verdict", "rule_id", "evidence_event_ids"}),
    "supervisor_decision": frozenset({"ticket_id", "decision", "evidence_event_ids"}),
    "legacy_event": frozenset({"source_seq", "source_kind", "source_hash"}),
    "tool_invocation": frozenset({"call_id", "tool_name", "args_digest"}),
    "tool_result": frozenset({"call_id", "tool_name", "status", "result_digest"}),
    "model_input_captured": frozenset({"input_ref", "input_sha256"}),
    "model_output_captured": frozenset({"output_ref", "output_sha256"}),
    "resource_read": frozenset({"resource_id", "message_ids", "ticket_id"}),
    "evidence_verified": frozenset({"ticket_id", "accepted", "owner"}),
    "task_state": frozenset({"ticket_id", "status", "owner"}),
}
_REQUIRED: dict[str, frozenset[str]] = {
    "attempt": _FIELDS["attempt"],
    "authorization_denial": _FIELDS["authorization_denial"],
    "accepted_write": frozenset({"message_id"}),
    "recipient_delivery": _FIELDS["recipient_delivery"],
    "recipient_observation": _FIELDS["recipient_observation"],
    "agent_discovery_report": _FIELDS["agent_discovery_report"],
    "monitor_alert": _FIELDS["monitor_alert"],
    "supervisor_decision": _FIELDS["supervisor_decision"],
    "legacy_event": _FIELDS["legacy_event"],
    "tool_invocation": _FIELDS["tool_invocation"],
    "tool_result": _FIELDS["tool_result"],
    "model_input_captured": _FIELDS["model_input_captured"],
    "model_output_captured": _FIELDS["model_output_captured"],
    "resource_read": frozenset({"resource_id", "message_ids"}),
    "evidence_verified": _FIELDS["evidence_verified"],
    "task_state": frozenset({"ticket_id", "status"}),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class TraceEvent:
    schema_version: int
    run_id: str
    event_id: str
    seq: int
    kind: str
    actor: str
    parent_event_ids: tuple[str, ...]
    data: dict[str, Any]
    prev_hash: str
    hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TraceV2:
    def __init__(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id or len(run_id) > 100:
            raise ValueError("A nonempty run_id of at most 100 characters is required")
        self.run_id = run_id
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def append(self, kind: str, actor: str, *, parents: Iterable[str] = (), **data: Any) -> TraceEvent:
        if kind not in KINDS or not isinstance(actor, str) or not actor:
            raise ValueError("Invalid event kind or actor")
        seq = len(self._events) + 1
        prev_hash = self._events[-1].hash if self._events else "0" * 64
        clean_data = json.loads(_canonical(data))
        parent_ids = tuple(parents)
        core = {
            "schema_version": SCHEMA_VERSION, "run_id": self.run_id,
            "event_id": f"e{seq:06d}", "seq": seq, "kind": kind, "actor": actor,
            "parent_event_ids": parent_ids, "data": clean_data, "prev_hash": prev_hash,
        }
        event = TraceEvent(**core, hash=hashlib.sha256(_canonical(core)).hexdigest())
        self._events.append(event)
        try:
            self.validate(complete=False)
        except (ValueError, KeyError, TypeError):
            self._events.pop()
            raise
        return event

    def validate(self, *, complete: bool = True) -> None:
        prev_hash = "0" * 64
        by_id: dict[str, TraceEvent] = {}
        attempts: dict[str, TraceEvent] = {}
        decisions: dict[str, TraceEvent] = {}
        deliveries: set[tuple[str, str]] = set()
        observations: set[tuple[str, str]] = set()
        for seq, event in enumerate(self._events, 1):
            if event.schema_version != SCHEMA_VERSION or event.run_id != self.run_id:
                raise ValueError("Schema version or run ID mismatch")
            if event.seq != seq or not _EVENT_ID.fullmatch(event.event_id) or event.event_id != f"e{seq:06d}":
                raise ValueError("Event sequence/ID mismatch")
            if event.kind not in KINDS or not isinstance(event.actor, str) or not event.actor:
                raise ValueError("Invalid kind or actor")
            if set(event.data) - _FIELDS[event.kind] or not _REQUIRED[event.kind] <= set(event.data):
                raise ValueError("Invalid data fields for event kind")
            if event.prev_hash != prev_hash or not _DIGEST.fullmatch(event.hash):
                raise ValueError("Broken event hash chain")
            core = event.as_dict()
            core.pop("hash")
            if hashlib.sha256(_canonical(core)).hexdigest() != event.hash:
                raise ValueError("Event digest mismatch")
            if len(set(event.parent_event_ids)) != len(event.parent_event_ids) or any(
                parent not in by_id for parent in event.parent_event_ids
            ):
                raise ValueError("Parent must be unique and precede child")
            data = event.data
            mid = data.get("message_id")
            if event.kind == "attempt":
                recipients = data["recipients"]
                if (not isinstance(mid, str) or not mid or mid in attempts
                        or not isinstance(data["route"], str) or not data["route"]
                        or not isinstance(recipients, list) or not recipients
                        or any(not isinstance(r, str) or not r or r == event.actor for r in recipients)
                        or len(set(recipients)) != len(recipients)
                        or not isinstance(data["payload_digest"], str)
                        or not _DIGEST.fullmatch(data["payload_digest"])):
                    raise ValueError("Invalid attempt provenance")
                attempts[mid] = event
            elif event.kind in {"authorization_denial", "accepted_write"}:
                attempt = attempts.get(mid)
                if not attempt or mid in decisions or event.parent_event_ids != (attempt.event_id,):
                    raise ValueError("Decision requires one unique attempt parent")
                if event.actor != attempt.actor:
                    raise ValueError("Decision actor differs from attempt")
                decisions[mid] = event
            elif event.kind == "recipient_delivery":
                recipient = data["recipient"]
                decision = decisions.get(mid)
                attempt = attempts.get(mid)
                if (not decision or decision.kind != "accepted_write" or not attempt
                        or recipient not in attempt.data["recipients"]
                        or event.parent_event_ids != (decision.event_id,)
                        or (mid, recipient) in deliveries):
                    raise ValueError("Delivery needs accepted write and intended recipient")
                deliveries.add((mid, recipient))
            elif event.kind == "recipient_observation":
                recipient = data["recipient"]
                parents = [by_id[p] for p in event.parent_event_ids]
                attempt = attempts.get(mid)
                if ((mid, recipient) not in deliveries or (mid, recipient) in observations
                        or event.actor != recipient or len(parents) != 1
                        or parents[0].kind != "recipient_delivery"
                        or parents[0].data["message_id"] != mid
                        or parents[0].data["recipient"] != recipient
                        or not isinstance(data["model_input_ref"], str) or not data["model_input_ref"]
                        or not attempt or data["payload_digest"] != attempt.data["payload_digest"]):
                    raise ValueError("Observation needs matching delivery and model input reference")
                observations.add((mid, recipient))
            elif event.kind == "agent_discovery_report":
                if not isinstance(data["resource_id"], str) or not data["resource_id"]:
                    raise ValueError("Report requires a resource")
            elif event.kind == "monitor_alert":
                if data["verdict"] not in {"alert", "no_alert", "abstain"}:
                    raise ValueError("Invalid monitor verdict")
                if data["evidence_event_ids"] != list(event.parent_event_ids):
                    raise ValueError("Alert evidence must match prior parent IDs")
            elif event.kind == "supervisor_decision":
                if data["decision"] not in {"approve", "refuse", "accept_assessment", "refuse_assessment", "approve_release"}:
                    raise ValueError("Invalid supervisor decision")
                if data["evidence_event_ids"] != list(event.parent_event_ids):
                    raise ValueError("Supervisor evidence must match prior parent IDs")
            elif event.kind in {"tool_invocation", "tool_result", "model_input_captured", "model_output_captured"}:
                digest = data.get("args_digest", data.get("result_digest", data.get("input_sha256", data.get("output_sha256"))))
                if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                    raise ValueError("Captured tool/model record needs SHA256")
            elif event.kind == "resource_read":
                if not isinstance(data["message_ids"], list) or len(set(data["message_ids"])) != len(data["message_ids"]):
                    raise ValueError("Resource read needs distinct message IDs")
            elif event.kind == "evidence_verified":
                if not isinstance(data["accepted"], bool):
                    raise ValueError("Evidence acceptance must be boolean")
            elif event.kind == "legacy_event":
                if not isinstance(data["source_seq"], int) or data["source_seq"] < 1:
                    raise ValueError("Invalid v1 source sequence")
            prev_hash = event.hash
            by_id[event.event_id] = event
        if complete and set(attempts) != set(decisions):
            raise ValueError("Each attempt must have one decision")

    def write_jsonl(self, path: Path, *, complete: bool = True) -> None:
        """Persist a complete trace, or explicitly preserve a crashed partial trace."""
        self.validate(complete=complete)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text("".join(json.dumps(e.as_dict(), sort_keys=True) + "\n" for e in self._events), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def read_jsonl(cls, path: Path, *, complete: bool = True) -> TraceV2:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise ValueError("Empty trace lacks a run ID")
        trace = cls(rows[0]["run_id"])
        for raw in rows:
            raw["parent_event_ids"] = tuple(raw["parent_event_ids"])
            trace._events.append(TraceEvent(**raw))
        trace.validate(complete=complete)
        return trace


def adapt_v1_fixture(events: Iterable[Event], *, run_id: str) -> TraceV2:
    """Copy authentic v1 facts; retain unsupported kinds as labeled legacy events.

    V1 `observed` means SimWorld.observe was called. It cannot establish actual
    model-input inclusion and is never mapped to recipient_observation.
    """
    trace = TraceV2(run_id)
    attempt_ids: dict[str, str] = {}
    decision_ids: dict[str, str] = {}
    for source in events:
        d = source.data
        if source.kind == "attempt":
            e = trace.append("attempt", source.actor, message_id=d["message_id"],
                             route=d["channel"], recipients=d["recipients"],
                             payload_digest=d["payload_digest"])
            attempt_ids[d["message_id"]] = e.event_id
        elif source.kind in {"send_denied", "send_accepted"}:
            mid = d["message_id"]
            kind = "authorization_denial" if source.kind == "send_denied" else "accepted_write"
            data = {"message_id": mid}
            if kind == "authorization_denial":
                data["reason_code"] = d.get("reason_code", "unspecified")
            else:
                data["resource_id"] = d["channel"]
            e = trace.append(kind, source.actor, parents=(attempt_ids[mid],), **data)
            decision_ids[mid] = e.event_id
        elif source.kind == "delivered":
            mid = d["message_id"]
            trace.append("recipient_delivery", source.actor, parents=(decision_ids[mid],),
                         message_id=mid, recipient=d["recipient"])
        elif source.kind == "channel_reported":
            trace.append("agent_discovery_report", source.actor,
                         resource_id=d["channel"], reason_code=d["reason_code"])
        else:
            trace.append("legacy_event", source.actor, source_seq=source.seq,
                         source_kind=source.kind, source_hash=source.hash)
    trace.validate()
    return trace
