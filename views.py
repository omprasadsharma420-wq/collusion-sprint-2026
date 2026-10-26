"""Explicit, bounded projections of trusted events for auditor replay."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from channels import SimWorld
from policy import AGENTS


class View(StrEnum):
    LOCAL = "local"
    POOLED_METADATA = "pooled_metadata"
    FULLER_TRACE = "fuller_trace"


_METADATA_KEYS = {
    "message_id", "channel", "recipients", "recipient", "sender", "ticket_id",
    "reason_code",
}


def replay(
    world: SimWorld, view: View, *, actor: str | None = None,
    until_seq: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return a new projection; never return Event, Message, or oracle objects."""
    if view == View.LOCAL and actor not in AGENTS:
        raise ValueError("A local replay needs a valid worker")
    if not isinstance(view, View):
        raise ValueError("Unknown auditor view")
    if until_seq is not None and until_seq < 0:
        raise ValueError("until_seq must be nonnegative")

    projected: list[dict[str, Any]] = []
    for event in world.log.events:
        if until_seq is not None and event.seq > until_seq:
            break
        if view == View.LOCAL and event.actor != actor and event.data.get("recipient") != actor:
            continue
        safe_data = {key: value for key, value in event.data.items() if key in _METADATA_KEYS}
        item = {"seq": event.seq, "kind": event.kind, "actor": event.actor, "data": safe_data}
        mid = event.data.get("message_id")
        if mid is not None and mid in world.messages:
            message = world.messages[mid]
            if view == View.FULLER_TRACE and event.kind in {
                "attempt", "send_accepted", "send_denied", "observed"
            }:
                item["data"]["body"] = message.body
            elif view == View.LOCAL and (
                event.kind == "attempt" and event.actor == actor
                or event.kind == "observed" and event.actor == actor
            ):
                item["data"]["body"] = message.body
        projected.append(item)
    return tuple(projected)


def write_replay(path: Path, frames: tuple[dict[str, Any], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(frame, sort_keys=True) + "\n" for frame in frames),
        encoding="utf-8",
    )
    temporary.replace(path)
