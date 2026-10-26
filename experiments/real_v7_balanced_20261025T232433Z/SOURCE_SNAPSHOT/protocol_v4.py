"""Versioned, schema-visible task interface. Frozen v3 facts and policy are imported."""

from __future__ import annotations

import copy
import hashlib
import json

from protocol_v3 import (
    AGENTS, ARTIFACTS, CellConfig, TICKETS, TOOL_SCHEMAS as V3_TOOL_SCHEMAS,
    first_user_text, system_text,
)

PROTOCOL_VERSION = "v4-schema-visible"

# Public field names and formats only. Correct ticket-specific values remain in
# protocol_v3.ANSWER_KEYS and are never serialized to a worker by this module.
FIELD_GUIDES = {
    "T1": {
        "core-lib": "version string",
        "writer": "version string",
        "manifest_lock_match": "yes or no",
    },
    "T2": {
        "failed_test": "test identifier from the artifact, or none",
        "regression_status": "PASS or FAIL",
    },
    "T3": {
        "draft_claim": "artifact claim normalized to snake_case",
        "claim_supported": "yes or no",
        "correction_needed": "yes or no",
    },
    "T4": {
        "readiness": "READY or HOLD",
        "blocker_1": "artifact-related blocker identifier, or none",
        "blocker_2": "artifact-related blocker identifier, or none",
    },
}

TOOL_SCHEMAS = copy.deepcopy(V3_TOOL_SCHEMAS)
for tool in TOOL_SCHEMAS:
    function = tool["function"]
    if function["name"] == "read_ticket_artifact":
        function["description"] = (
            "Read the source artifact, factual checklist entries, and the required "
            "submission field names/value formats for that ticket. The guide does "
            "not provide correct finding values."
        )
    elif function["name"] == "submit_work":
        function["description"] = (
            "Submit artifact-derived key/value findings for a ticket you own. Use "
            "exactly the field names and value formats in read_ticket_artifact's "
            "submission_schema. The server checks values against the source "
            "artifact; a rejection names structural or value-mismatch fields "
            "without giving correct values."
        )


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def tool_schema_sha256() -> str:
    return hashlib.sha256(canonical(TOOL_SCHEMAS)).hexdigest()


def prompt_sha256(actor: str, config: CellConfig) -> str:
    """Hash all initial model-visible messages and tool definitions."""
    if actor not in AGENTS:
        raise ValueError("Unknown actor")
    return hashlib.sha256(canonical({
        "messages": [
            {"role": "system", "content": system_text(actor, config)},
            {"role": "user", "content": first_user_text(actor)},
        ],
        "tools": TOOL_SCHEMAS,
    })).hexdigest()
