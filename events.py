"""Deterministic trusted event and oracle recording, with an integrity chain."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def payload_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Event:
    seq: int
    kind: str
    actor: str
    data: dict[str, Any]
    prev_hash: str
    hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def append(self, kind: str, actor: str, **data: Any) -> Event:
        seq = len(self._events) + 1
        prev_hash = self._events[-1].hash if self._events else "0" * 64
        clean_data = json.loads(_canonical(data))
        core = {"seq": seq, "kind": kind, "actor": actor, "data": clean_data, "prev_hash": prev_hash}
        digest = hashlib.sha256(_canonical(core)).hexdigest()
        event = Event(seq, kind, actor, clean_data, prev_hash, digest)
        self._events.append(event)
        return event

    def validate(self) -> None:
        """Fail on tampering, gaps, or impossible message-state transitions."""
        prev_hash = "0" * 64
        attempts: dict[str, set[str]] = {}
        decided: set[str] = set()
        accepted: set[str] = set()
        delivered: set[tuple[str, str]] = set()
        observed: set[tuple[str, str]] = set()
        for expected_seq, event in enumerate(self._events, 1):
            if event.seq != expected_seq or event.prev_hash != prev_hash:
                raise ValueError("Event sequence or predecessor hash is invalid")
            core = {"seq": event.seq, "kind": event.kind, "actor": event.actor,
                    "data": event.data, "prev_hash": event.prev_hash}
            if hashlib.sha256(_canonical(core)).hexdigest() != event.hash:
                raise ValueError(f"Event {event.seq} checksum is invalid")
            mid = event.data.get("message_id")
            if event.kind == "attempt":
                if mid in attempts:
                    raise ValueError("Duplicate message attempt")
                attempts[mid] = set(event.data.get("recipients", []))
            elif event.kind in {"send_accepted", "send_denied"}:
                if mid not in attempts or mid in decided:
                    raise ValueError("Message decision without a unique attempt")
                decided.add(mid)
                if event.kind == "send_accepted":
                    accepted.add(mid)
            elif event.kind == "delivered":
                pair = (mid, event.data["recipient"])
                if mid not in accepted or pair in delivered or event.data["recipient"] not in attempts[mid]:
                    raise ValueError("Delivery without acceptance or duplicate delivery")
                delivered.add(pair)
            elif event.kind == "observed":
                pair = (mid, event.actor)
                if pair not in delivered or pair in observed:
                    raise ValueError("Observation without delivery or duplicate observation")
                observed.add(pair)
            prev_hash = event.hash
        if set(attempts) != decided:
            raise ValueError("An attempted message lacks a decision")

    def write_jsonl(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(e.as_dict(), sort_keys=True) + "\n" for e in self._events),
            encoding="utf-8",
        )
        temporary.replace(path)

    @classmethod
    def read_jsonl(cls, path: Path) -> EventLog:
        log = cls()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            log._events.append(Event(**raw))
        log.validate()
        return log


@dataclass(slots=True)
class TruthLedger:
    """Fixture annotations and private payloads; never passed to auditor projections."""

    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenario: str = ""

    def record_message(
        self, message_id: str, *, body: str, category: str,
        ticket_id: str | None = None, scheme_id: str | None = None,
    ) -> None:
        self.messages[message_id] = {
            "body": body,
            "category": category,
            "ticket_id": ticket_id,
            "scheme_id": scheme_id,
        }

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy({"scenario": self.scenario, "messages": self.messages})

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
