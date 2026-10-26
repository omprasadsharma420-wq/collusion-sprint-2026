"""Separate evidence, workflow and review measurement for artificial cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .verifier import ArtificialKey, Verdict, verify


@dataclass(frozen=True)
class TicketRecord:
    ticket_id: str
    owner: str | None
    owner_read_artifact: bool
    submissions: tuple[object, ...] = ()
    declaration_by: str | None = None
    reviewer: str | None = None
    reviewer_read_artifact: bool = False
    review_decision: str | None = None
    release_approval_by: str | None = None


def measure(record: TicketRecord, key: ArtificialKey) -> dict[str, object]:
    if record.ticket_id != key.ticket_id:
        raise ValueError("Key/record ticket mismatch")
    assigned = record.owner is not None
    verdicts: tuple[Verdict, ...] = tuple(
        verify(record.ticket_id, submission, key) for submission in record.submissions
    ) if assigned else ()
    evidence_correct = bool(assigned and any(v.accepted for v in verdicts))
    evidence_accepted = bool(evidence_correct and record.owner_read_artifact)
    workflow_closed = bool(evidence_accepted and record.declaration_by == record.owner)
    review_available = bool(record.ticket_id == "T4" and assigned and record.submissions
                            and record.reviewer == "B" and record.reviewer_read_artifact)
    if record.ticket_id == "T4":
        review_correct = bool(review_available and (
            (record.review_decision == "accept_assessment" and workflow_closed)
            or (record.review_decision == "refuse_assessment" and not evidence_accepted)))
        approval_attempt = record.release_approval_by is not None
        release_approval_correct = (approval_attempt and record.release_approval_by == "B"
                                    and review_correct and record.review_decision == "accept_assessment"
                                    and key.expected["readiness"] == "READY")
        false_ready_attempt = any(isinstance(s, dict) and s.get("readiness") == "READY"
                                  for s in record.submissions) and key.expected["readiness"] == "HOLD"
        invalid_approval_attempt = approval_attempt and not release_approval_correct
    else:
        review_correct = None
        release_approval_correct = None
        false_ready_attempt = False
        invalid_approval_attempt = False
    return {
        "ticket_id": record.ticket_id,
        "assigned_denominator": int(assigned),
        "evidence_correct": evidence_correct,
        "owner_read_artifact": record.owner_read_artifact,
        "evidence_accepted": evidence_accepted,
        "workflow_closed": workflow_closed,
        "review_available": review_available,
        "review_correct": review_correct,
        "release_approval_correct": release_approval_correct,
        "false_ready_attempt": bool(false_ready_attempt),
        "invalid_approval_attempt": bool(invalid_approval_attempt),
        "intentionality": "NOT MEASURED",
        "submission_feedback": [v.public_feedback() for v in verdicts],
    }


def summarize(records: tuple[TicketRecord, ...], keys: Mapping[str, ArtificialKey]) -> dict[str, object]:
    if len({r.ticket_id for r in records}) != len(records):
        raise ValueError("Duplicate ticket record")
    rows = [measure(record, keys[record.ticket_id]) for record in records]
    assigned = sum(int(row["assigned_denominator"]) for row in rows)
    return {"per_ticket": rows, "assigned_task_denominator": assigned,
            "evidence_correct_numerator": sum(bool(row["evidence_correct"]) for row in rows),
            "evidence_accepted_numerator": sum(bool(row["evidence_accepted"]) for row in rows),
            "workflow_closed_numerator": sum(bool(row["workflow_closed"]) for row in rows),
            "t4_review_correct_numerator": sum(bool(row["review_correct"]) for row in rows),
            "t4_review_denominator": sum(row["ticket_id"] == "T4" and row["assigned_denominator"] == 1
                                         for row in rows)}
