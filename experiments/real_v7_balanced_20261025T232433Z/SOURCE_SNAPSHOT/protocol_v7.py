"""Approved V7 visible interface: exact frozen text and ordered tool JSON.

No hidden answer key is imported or serialized by this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from protocol_v3 import AGENTS, ARTIFACTS, CellConfig
from world_v3 import canonical

PROTOCOL_VERSION = "v7-balanced-natural"
_ROOT = Path(__file__).resolve().parent / "v7_approved_interface"
_PROMPTS = json.loads((_ROOT / "prompts.json").read_text(encoding="utf-8"))
TOOL_SCHEMAS = json.loads((_ROOT / "tools.json").read_text(encoding="utf-8"))


def system_text(actor: str, config: CellConfig) -> str:
    if actor not in AGENTS:
        raise ValueError("Unknown actor")
    return _PROMPTS["system"]["ON" if config.reporting_reminder else "OFF"][actor]


def first_user_text(actor: str) -> str:
    if actor not in AGENTS:
        raise ValueError("Unknown actor")
    return _PROMPTS["first_user"][actor]


def prompt_sha256(actor: str, config: CellConfig) -> str:
    return hashlib.sha256(canonical({"messages": [
        {"role": "system", "content": system_text(actor, config)},
        {"role": "user", "content": first_user_text(actor)},
    ], "tools": TOOL_SCHEMAS})).hexdigest()


def tool_schema_sha256() -> str:
    return hashlib.sha256(canonical(TOOL_SCHEMAS)).hexdigest()


def public_submission_choices(ticket_id: str) -> dict[str, list[str]]:
    """Only the already model-visible choices for this ticket."""
    if ticket_id not in ARTIFACTS:
        raise ValueError("Unknown ticket")
    from verifier_v7 import REQUIRED_FIELDS
    submit = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "submit_work")
    properties = submit["function"]["parameters"]["properties"]["findings"]["properties"]
    return {field: copy.deepcopy(properties[field]["enum"])
            for field in REQUIRED_FIELDS[ticket_id]}
