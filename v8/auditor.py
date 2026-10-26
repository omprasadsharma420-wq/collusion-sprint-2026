"""V8 shadow-auditor information contract. Neither monitor can write to actors."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import evaluate_cutoff
from protocol_v3 import MEMO_MARKER
from v8.protocol import M1_SYSTEM, P_PRIVATE_NOTES

ELIGIBLE_KINDS = frozenset({"accepted_write", "authorization_denial", "supervisor_decision"})
M1_MESSAGE_ROUTES = frozenset({"team_board", "known_direct", "release_checklist",
                               "supervisor_direct", "supervisor_reply", "workspace_notification"})


def sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()


def eligible_cutoffs(trace) -> list[str]:
    """Common M0/M1 candidate universe, ordered before looking at model outcomes."""
    return [e.event_id for e in trace.events if e.kind in ELIGIBLE_KINDS and
            (e.kind != "supervisor_decision" or e.data.get("ticket_id") == "T4")]


def m0_at_time(trace, cutoff_event_id: str) -> dict[str, Any]:
    cutoff = next(e for e in trace.events if e.event_id == cutoff_event_id)
    frames = project(trace, AuditView.POOLED_METADATA, until_seq=cutoff.seq)
    decisions = evaluate_cutoff(frames, cutoff_seq=cutoff.seq)
    return {"cutoff_event_id": cutoff_event_id, "cutoff_seq": cutoff.seq,
            "input_frames": list(frames), "verdicts": list(decisions),
            "status": "NOT_EVALUATED" if not decisions else "EVALUATED"}


def _redact_exact_private(text: str) -> str:
    result = text.replace(MEMO_MARKER, "[REDACTED]")
    for note in P_PRIVATE_NOTES.values():
        result = result.replace(note, "[REDACTED]")
    return result


def m1_at_time(trace, messages: dict[str, dict], cutoff_event_id: str) -> dict[str, Any]:
    """Build an immutable at-time slice; no private prompts, truth, arm or future."""
    cutoff = next(e for e in trace.events if e.event_id == cutoff_event_id)
    frames = list(project(trace, AuditView.POOLED_METADATA, until_seq=cutoff.seq))
    accepted = {e.data["message_id"]: e for e in trace.events if
                e.kind == "accepted_write" and e.seq <= cutoff.seq}
    work_messages = []
    for mid, event in accepted.items():
        message = messages[mid]
        if message["route"] not in M1_MESSAGE_ROUTES:
            continue
        work_messages.append({"message_id": mid, "accepted_write_event_id": event.event_id,
                              "sender": message["actor"], "route": message["route"],
                              "recipients": list(message["recipients"]),
                              "body": _redact_exact_private(message["body"]),
                              "origin": message.get("origin", "MODEL_ACTION")})
    result = {"cutoff_event_id": cutoff_event_id, "cutoff_seq": cutoff.seq,
              "metadata_frames": frames, "workplace_messages": work_messages,
              "information_contract": "AT_TIME_ALLOWLISTED_WORKPLACE_CONTENT_ONLY"}
    raw = json.dumps(result, ensure_ascii=False)
    assert MEMO_MARKER not in raw
    assert all(note not in raw for note in P_PRIVATE_NOTES.values())
    assert not any(key in result for key in ("arm", "hidden_truth", "human_labels"))
    assert all(frame["seq"] <= cutoff.seq for frame in frames)
    return result


def m1_messages(slice_: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "system", "content": M1_SYSTEM},
            {"role": "user", "content": json.dumps(slice_, sort_keys=True,
                                                     ensure_ascii=False)}]
