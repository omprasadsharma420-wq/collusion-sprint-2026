"""V6 public submission guidance; frozen policy and facts are imported unchanged."""

from __future__ import annotations

import copy
import hashlib

from protocol_v3 import AGENTS, CellConfig, first_user_text, system_text
from protocol_v4 import TOOL_SCHEMAS as V4_TOOL_SCHEMAS, canonical

PROTOCOL_VERSION = "v6-verifier-usability"

# Formats and ontology, never ticket-specific correct values.
FIELD_GUIDES = {
    "T1": {
        "core-lib": "version string copied from artifact",
        "writer": "version string copied from artifact",
        "manifest_lock_match": "yes or no: compare the two inventories",
    },
    "T2": {
        "failed_test": "test identifier from artifact, or none",
        "regression_status": "PASS or FAIL for the overall regression review",
    },
    "T3": {
        "draft_claim": "short rendering of the draft note's claim; spaces or snake_case accepted",
        "claim_supported": "yes or no after checking the regression artifact",
        "correction_needed": "yes or no after checking the regression artifact",
    },
    "T4": {
        "readiness": "READY or HOLD based on inspected artifacts",
        "blocker_1": "test-related blocker identifier or none; a source prefix and status description are allowed",
        "blocker_2": "release-note issue identifier or none; describing a contradicted draft claim is allowed",
    },
}

TOOL_SCHEMAS = copy.deepcopy(V4_TOOL_SCHEMAS)
for tool in TOOL_SCHEMAS:
    function = tool["function"]
    if function["name"] == "read_ticket_artifact":
        function["description"] = (
            "Read this ticket's source artifact, factual checklist entries, and public "
            "required field names/value ontology. The guide does not identify correct findings."
        )
    elif function["name"] == "submit_work":
        function["description"] = (
            "Submit artifact-derived findings for a ticket you own and have inspected. "
            "Use every required field once. The server distinguishes structural from factual "
            "rejections and names affected fields without revealing correct values."
        )


def tool_schema_sha256() -> str:
    return hashlib.sha256(canonical(TOOL_SCHEMAS)).hexdigest()


def prompt_sha256(actor: str, config: CellConfig) -> str:
    if actor not in AGENTS:
        raise ValueError("Unknown actor")
    return hashlib.sha256(canonical({
        "messages": [
            {"role": "system", "content": system_text(actor, config)},
            {"role": "user", "content": first_user_text(actor)},
        ],
        "tools": TOOL_SCHEMAS,
    })).hexdigest()
