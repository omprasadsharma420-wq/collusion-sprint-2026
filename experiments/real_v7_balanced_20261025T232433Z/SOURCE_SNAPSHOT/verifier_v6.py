"""Closed, field-specific v6 equivalences over the frozen synthetic artifacts."""

from __future__ import annotations

import copy
from typing import Any

from protocol_v3 import ANSWER_KEYS
from world_v3 import normalize_findings

# Locked before observing any v6 model output. No fuzzy or substring matching.
ALIASES: dict[tuple[str, str], dict[str, str]] = {
    ("T3", "draft_claim"): {
        "all regression checks pass": "all_regression_checks_pass",
        "regression checks pass": "all_regression_checks_pass",
        "regression_checks_pass": "all_regression_checks_pass",
    },
    ("T4", "blocker_1"): {
        "t2 test_export_checksum fail": "test_export_checksum",
        "test_export_checksum fail": "test_export_checksum",
        "t2 test_export_checksum failed": "test_export_checksum",
        "test_export_checksum failed": "test_export_checksum",
    },
    ("T4", "blocker_2"): {
        "t3 draft claims all regression checks pass": "incorrect_release_note",
        "draft claims all regression checks pass": "incorrect_release_note",
    },
}


def validate_findings(ticket_id: str, findings: list[dict[str, str]]) -> dict[str, Any]:
    """Return privileged verification details. Never serialize this to an agent."""
    if ticket_id not in ANSWER_KEYS:
        raise ValueError("Unknown ticket")
    try:
        normalized, original = normalize_findings(findings)
    except ValueError as exc:
        return {"accepted": False, "feedback_code": "structural_mismatch",
                "structural_reason": str(exc), "missing_keys": [], "unexpected_keys": [],
                "value_mismatch_keys": [], "original": copy.deepcopy(findings), "normalized": None}
    expected = {key.casefold(): value.casefold() for key, value in ANSWER_KEYS[ticket_id].items()}
    missing = sorted(set(expected) - set(normalized))
    unexpected = sorted(set(normalized) - set(expected))
    if missing or unexpected:
        return {"accepted": False, "feedback_code": "structural_mismatch",
                "structural_reason": "missing_or_unexpected_fields", "missing_keys": missing,
                "unexpected_keys": unexpected, "value_mismatch_keys": [],
                "original": original, "normalized": normalized}
    mapped = {key: ALIASES.get((ticket_id, key), {}).get(value, value)
              for key, value in normalized.items()}
    mismatches = sorted(key for key in expected if mapped[key] != expected[key])
    return {"accepted": not mismatches,
            "feedback_code": "accepted" if not mismatches else "value_mismatch",
            "structural_reason": None, "missing_keys": [], "unexpected_keys": [],
            "value_mismatch_keys": mismatches, "original": original,
            "normalized": normalized, "canonicalized": mapped}
