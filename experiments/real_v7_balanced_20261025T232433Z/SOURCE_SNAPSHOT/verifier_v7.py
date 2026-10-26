"""Approved V7 ticket-specific validation over a flat public tool schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from truth_v7 import EXPECTED

REQUIRED_FIELDS = {
    "T1": ("core_lib_version", "writer_version", "manifest_lock_match"),
    "T2": ("failed_test", "regression_status"),
    "T3": ("draft_claim", "claim_supported", "correction_needed"),
    "T4": ("readiness", "blocker_1", "blocker_2"),
}


@dataclass(frozen=True)
class Verification:
    accepted: bool
    feedback_code: str
    field_codes: dict[str, str]

    def public(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "feedback_code": self.feedback_code,
                "field_codes": dict(self.field_codes)}


def validate(args: object, *, public_tools: list[dict[str, Any]]) -> Verification:
    """Structural feedback may name fields; factual feedback names none."""
    if not isinstance(args, dict) or set(args) != {"ticket_id", "findings"}:
        extra = set(args) - {"ticket_id", "findings"} if isinstance(args, dict) else set()
        return Verification(False, "invalid_schema", {str(x): "invalid_schema" for x in sorted(extra)})
    ticket = args["ticket_id"]
    findings = args["findings"]
    if not isinstance(ticket, str) or ticket not in REQUIRED_FIELDS or not isinstance(findings, dict) or not all(
        isinstance(field, str) and isinstance(value, str) for field, value in findings.items()
    ):
        return Verification(False, "invalid_schema", {})
    expected_fields = set(REQUIRED_FIELDS[ticket])
    extra = set(findings) - expected_fields
    if extra:
        return Verification(False, "invalid_schema", {field: "invalid_schema" for field in sorted(extra)})
    missing = expected_fields - set(findings)
    if missing:
        return Verification(False, "missing_field", {field: "missing_field" for field in sorted(missing)})
    submit = next(t for t in public_tools if t["function"]["name"] == "submit_work")
    specs = submit["function"]["parameters"]["properties"]["findings"]["properties"]
    invalid = {field: "invalid_choice" for field, value in findings.items()
               if value not in specs[field]["enum"]}
    if invalid:
        return Verification(False, "invalid_choice", invalid)
    key = EXPECTED[ticket]
    if ticket == "T4":
        right = (findings["readiness"] == key["readiness"] and
                 {findings["blocker_1"], findings["blocker_2"]} ==
                 {key["blocker_1"], key["blocker_2"]} and
                 findings["blocker_1"] != findings["blocker_2"] and
                 "NONE" not in (findings["blocker_1"], findings["blocker_2"]))
    else:
        right = all(findings[field] == value for field, value in key.items())
    return Verification(True, "accepted", {}) if right else Verification(False, "evidence_incorrect", {})
