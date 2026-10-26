"""Allowlisted, time-bounded v2 auditor exports. No truth store is an input."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from trace_v2 import TraceV2


class AuditView(StrEnum):
    LOCAL = "local"
    POOLED_METADATA = "pooled_metadata"
    FULLER_TRACE = "fuller_trace"


_SAFE_FIELDS = {
    "attempt": ("message_id", "route", "recipients"),
    "authorization_denial": ("message_id", "reason_code"),
    "accepted_write": ("message_id", "resource_id"),
    "recipient_delivery": ("message_id", "recipient"),
    "recipient_observation": ("message_id", "recipient"),
    "agent_discovery_report": ("resource_id", "reason_code"),
    "supervisor_decision": ("ticket_id", "decision"),
    "tool_invocation": ("call_id", "tool_name"),
    "tool_result": ("call_id", "tool_name", "status"),
    "resource_read": ("resource_id", "message_ids", "ticket_id"),
    "evidence_verified": ("ticket_id", "accepted", "owner"),
    "task_state": ("ticket_id", "status", "owner"),
}


def project(trace: TraceV2, view: AuditView, *, actor: str | None = None,
            until_seq: int | None = None) -> tuple[dict[str, Any], ...]:
    """Project metadata only. FULLER_TRACE reserves a view name; content needs approval.

    The trace must be supplied without oracle, condition, or secret-bearing sidecars.
    This serializer is an information contract, not an OS access boundary.
    """
    trace.validate()
    if not isinstance(view, AuditView):
        raise ValueError("Unknown audit view")
    if view == AuditView.LOCAL and actor not in {"A", "B", "C", "D"}:
        raise ValueError("Local view requires one worker")
    if until_seq is not None and (not isinstance(until_seq, int) or until_seq < 0):
        raise ValueError("Invalid cutoff")
    frames: list[dict[str, Any]] = []
    for event in trace.events:
        if until_seq is not None and event.seq > until_seq:
            break
        if event.kind not in _SAFE_FIELDS:  # No monitor feedback or unlabeled legacy content.
            continue
        if view == AuditView.LOCAL and event.actor != actor and event.data.get("recipient") != actor:
            continue
        frames.append({
            "event_id": event.event_id,
            "seq": event.seq,
            "kind": event.kind,
            "actor": event.actor,
            "parent_event_ids": list(event.parent_event_ids),
            "data": {key: event.data[key] for key in _SAFE_FIELDS[event.kind] if key in event.data},
        })
    return tuple(frames)


def write_projection(path: Path, frames: tuple[dict[str, Any], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(frame, sort_keys=True) + "\n" for frame in frames),
        encoding="utf-8",
    )
    temporary.replace(path)
