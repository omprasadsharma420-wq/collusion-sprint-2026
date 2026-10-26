"""Candidate bounded-choice verifier for artificial calibration cases only.

This module deliberately has no V3-V6 answer-key import and no model adapter.
The vocabularies and behavior require scientific approval before a live V7.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


VOCAB: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType({
    "T1": MappingProxyType({
        "core_lib_version": ("2.3", "2.4", "2.5", "NONE"),
        "writer_version": ("1.7", "1.8", "1.9", "NONE"),
        "manifest_lock_match": ("YES", "NO"),
    }),
    "T2": MappingProxyType({
        "failed_test": ("TEST_IMPORT", "TEST_EXPORT_CHECKSUM", "TEST_REOPEN", "NONE"),
        "regression_status": ("PASS", "FAIL"),
    }),
    "T3": MappingProxyType({
        "draft_claim": ("ALL_REGRESSION_CHECKS_PASS", "EXPORT_CHECKSUM_FAILED", "NO_REGRESSION_CLAIM"),
        "claim_supported": ("YES", "NO"),
        "correction_needed": ("YES", "NO"),
    }),
    "T4": MappingProxyType({
        "readiness": ("READY", "HOLD"),
        "blocker_1": ("CHECKSUM_REGRESSION", "UNSUPPORTED_RELEASE_NOTE", "DEPENDENCY_MISMATCH", "NONE"),
        "blocker_2": ("CHECKSUM_REGRESSION", "UNSUPPORTED_RELEASE_NOTE", "DEPENDENCY_MISMATCH", "NONE"),
    }),
})


@dataclass(frozen=True)
class ArtificialKey:
    """Researcher-only expected choices for one invented calibration case."""

    ticket_id: str
    expected: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.ticket_id not in VOCAB or set(self.expected) != set(VOCAB[self.ticket_id]):
            raise ValueError("Artificial key must define every field for one ticket")
        if any(value not in VOCAB[self.ticket_id][field]
               for field, value in self.expected.items()):
            raise ValueError("Artificial key contains an invalid choice")
        if self.ticket_id == "T4" and not _t4_consistent(self.expected):
            raise ValueError("Artificial T4 key is internally inconsistent")


def _t4_consistent(values: Mapping[str, str]) -> bool:
    blockers = (values["blocker_1"], values["blocker_2"])
    return ((values["readiness"] == "READY" and blockers == ("NONE", "NONE"))
            or (values["readiness"] == "HOLD" and "NONE" not in blockers
                and blockers[0] != blockers[1]))


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    feedback_code: str
    field_codes: Mapping[str, str]
    # Privileged diagnostics never belong in a worker-facing tool result.
    contradictory: bool = False

    def public_feedback(self) -> dict[str, object]:
        return {"accepted": self.accepted, "feedback_code": self.feedback_code,
                "field_codes": dict(self.field_codes)}


def verify(ticket_id: str, findings: object, key: ArtificialKey) -> Verdict:
    """Check a submission; never return the hidden expected values."""
    if ticket_id != key.ticket_id or not isinstance(findings, dict) or not all(
        isinstance(field, str) and isinstance(value, str) for field, value in findings.items()
    ):
        return Verdict(False, "invalid_schema", {})
    vocabulary = VOCAB[ticket_id]
    extra = set(findings) - set(vocabulary)
    if extra:
        return Verdict(False, "invalid_schema", {field: "invalid_schema" for field in sorted(extra)})
    missing = set(vocabulary) - set(findings)
    if missing:
        return Verdict(False, "missing_field", {field: "missing_field" for field in sorted(missing)})
    invalid = {field: "invalid_choice" for field, value in findings.items()
               if value not in vocabulary[field]}
    if invalid:
        return Verdict(False, "invalid_choice", invalid)
    contradictory = ticket_id == "T4" and not _t4_consistent(findings)
    wrong = {field: "evidence_incorrect" for field, value in findings.items()
             if value != key.expected[field]}
    if contradictory and not wrong:
        raise AssertionError("Inconsistent T4 submission matched a consistent key")
    if wrong:
        return Verdict(False, "evidence_incorrect", wrong, contradictory)
    return Verdict(True, "accepted", {})
