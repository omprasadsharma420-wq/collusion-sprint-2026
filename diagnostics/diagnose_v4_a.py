"""Read-only forensic tables for the immutable v4 Cell A episode."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from protocol_v3 import AGENTS, ANSWER_KEYS, ARTIFACTS, MEMO_MARKER
from protocol_v4 import prompt_sha256, tool_schema_sha256
from run_real_modal_v4 import validate_cell
from trace_v2 import TraceV2
from world_v4 import WorldV4

RUN = ROOT / "experiments/real_v4_schema_visible_20261025T160532Z"
CELL = RUN / "A"
OUT = RUN / "researcher/v4_a_diagnosis"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def csv_write(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def content_in_input(event, *, message_id: str, body: str) -> bool:
    request = load(CELL / "trusted" / event.data["input_ref"])
    for item in request["messages"]:
        if item.get("role") != "tool":
            continue
        try:
            parsed = json.loads(item["content"])
        except (ValueError, KeyError):
            continue
        if any(obj.get("message_id") == message_id and obj.get("body") == body
               for obj in parsed.get("items", [])):
            return True
    return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trace = TraceV2.read_jsonl(CELL / "trusted/events_v2.jsonl")
    trace.validate()
    events = list(trace.events)
    by_id = {event.event_id: event for event in events}
    tools = load(CELL / "trusted/tool_calls.json")
    evidence = load(CELL / "trusted/evidence.json")
    messages = load(CELL / "trusted/messages.json")
    manifest = load(CELL / "manifest.json")
    validation = validate_cell(RUN, "A", manifest, provider_start=1, provider_stop=47)
    inputs = [e for e in events if e.kind == "model_input_captured"]
    outputs = [e for e in events if e.kind == "model_output_captured"]
    invocations = {e.data["call_id"]: e for e in events if e.kind == "tool_invocation"}
    results = {e.data["call_id"]: e for e in events if e.kind == "tool_result"}
    by_call = {call["call_id"]: call for call in tools}
    assert len(inputs) == len(outputs) == 47

    turns = []
    actor_turns = Counter()
    for i, (input_event, output_event) in enumerate(zip(inputs, outputs), 1):
        assert input_event.actor == output_event.actor
        actor = input_event.actor
        actor_turns[actor] += 1
        next_seq = inputs[i].seq if i < len(inputs) else len(events) + 1
        actions = [e for e in events if output_event.seq < e.seq < next_seq
                   and e.kind == "tool_invocation"]
        assert len(actions) <= 1
        invocation = actions[0] if actions else None
        call = by_call[invocation.data["call_id"]] if invocation else None
        result = call["result"] if call else {}
        turns.append({
            "provider_call": i, "actor": actor, "actor_turn": actor_turns[actor],
            "input_event_id": input_event.event_id,
            "output_event_id": output_event.event_id,
            "tool_invocation_event_id": invocation.event_id if invocation else "",
            "tool_result_event_id": results[call["call_id"]].event_id if call else "",
            "tool_call_id": call["call_id"] if call else "",
            "tool_name": call["tool_name"] if call else "FINAL_TEXT",
            "ticket_id": call["arguments"].get("ticket_id", "") if call else "",
            "result_ok": result.get("ok", "") if call else "",
            "result_reason_code": result.get("reason_code", result.get("reason", "")) if call else "",
            "model_output_kind": "tool_call" if call else "final",
        })
    csv_write(OUT / "V4_A_TURNS.csv", turns, list(turns[0]))

    ticket_chains = []
    for ticket in "T1", "T2", "T3", "T4":
        assign = [c for c in tools if c["tool_name"] == "assign_ticket"
                  and c["arguments"]["ticket_id"] == ticket and c["result"]["ok"]]
        assert len(assign) == 1
        owner = assign[0]["actor"]
        reads = []
        for call in tools:
            if call["tool_name"] != "read_ticket_artifact" or call["actor"] != owner:
                continue
            if call["arguments"]["ticket_id"] != ticket or not call["result"]["ok"]:
                continue
            result_event = results[call["call_id"]]
            next_input = next((e for e in inputs if e.actor == owner and e.seq > result_event.seq), None)
            included = False
            if next_input:
                request = load(CELL / "trusted" / next_input.data["input_ref"])
                for item in request["messages"]:
                    if item.get("role") != "tool":
                        continue
                    try:
                        item_result = json.loads(item["content"])
                    except (ValueError, KeyError):
                        continue
                    included |= (item_result.get("ticket_id") == ticket and
                                 item_result.get("artifact") == ARTIFACTS[ticket])
            reads.append({"call_id": call["call_id"],
                          "tool_result_event_id": result_event.event_id,
                          "next_owner_input_event_id": next_input.event_id if next_input else None,
                          "artifact_in_next_input": included})
        submissions = []
        for call in tools:
            if call["tool_name"] != "submit_work" or call["arguments"]["ticket_id"] != ticket:
                continue
            item = next(e for e in evidence if e["event_id"] == call["result"]["evidence_event_id"])
            submissions.append({"call_id": call["call_id"],
                                "invocation_event_id": invocations[call["call_id"]].event_id,
                                "evidence_event_id": item["event_id"],
                                "accepted": item["accepted"],
                                "verifier_reason": item["reason"],
                                "feedback_reason_code": call["result"].get("reason_code"),
                                "mismatch_keys": call["result"].get("value_mismatch_keys", [])})
        closes = [e.event_id for e in events if e.kind == "task_state"
                  and e.data.get("ticket_id") == ticket
                  and e.data.get("status") == "analysis_declared"]
        ticket_chains.append({"ticket_id": ticket, "owner": owner,
                              "assignment_call_id": assign[0]["call_id"],
                              "assignment_event_id": next(e.event_id for e in events
                                  if e.kind == "task_state" and e.data.get("ticket_id") == ticket
                                  and e.data.get("status") == "assigned"),
                              "artifact_reads": reads, "submissions": submissions,
                              "declare_complete_event_ids": closes,
                              "verified_completion": ticket in load(CELL / "trusted/outcome.json")["valid_ticket_analyses"]})
    write(OUT / "TICKET_STATE_CHAINS.json", ticket_chains)

    deliveries = []
    for mid, message in messages.items():
        attempt = next(e for e in events if e.kind == "attempt" and e.data["message_id"] == mid)
        accepted = next(e for e in events if e.kind == "accepted_write" and e.data["message_id"] == mid)
        for recipient in message["recipients"]:
            delivery = next(e for e in events if e.kind == "recipient_delivery"
                            and e.data["message_id"] == mid and e.data["recipient"] == recipient)
            matching_reads = [e for e in events if e.kind == "resource_read"
                              and e.actor == recipient and e.seq > delivery.seq
                              and e.data["resource_id"] == message["route"]
                              and (message["route"] != "release_checklist" or
                                   e.data.get("ticket_id") == message.get("ticket_id"))]
            containing_reads = [e for e in matching_reads if mid in e.data["message_ids"]]
            actual_inputs = [e for e in inputs if e.actor == recipient and e.seq > delivery.seq
                             and content_in_input(e, message_id=mid, body=message["body"])]
            observations = [e for e in events if e.kind == "recipient_observation"
                            and e.data["message_id"] == mid and e.actor == recipient]
            expected_observation = bool(actual_inputs)
            deliveries.append({
                "message_id": mid, "attempt_event_id": attempt.event_id,
                "accepted_event_id": accepted.event_id,
                "payload_digest": message["payload_digest"],
                "route": message["route"], "target_resource": message["route"],
                "ticket_id": message.get("ticket_id", ""),
                "authorization": "accepted", "sender": message["actor"],
                "recipient": recipient, "delivery_event_id": delivery.event_id,
                "later_corresponding_read_event_ids": ";".join(e.event_id for e in matching_reads),
                "read_returned_message_event_ids": ";".join(e.event_id for e in containing_reads),
                "exact_body_in_next_or_later_input_event_ids": ";".join(e.event_id for e in actual_inputs),
                "recipient_observation_event_ids": ";".join(e.event_id for e in observations),
                "missing_observation_defect": expected_observation and not observations,
            })
    csv_write(OUT / "DELIVERY_READ_INPUT_AUDIT.csv", deliveries, list(deliveries[0]))

    pooled = project(trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(pooled)
    saved_verdicts = [json.loads(line) for line in
                      (CELL / "auditor/verdicts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert list(verdicts) == saved_verdicts
    frame_by_id = {frame["event_id"]: frame for frame in pooled}
    auditor = [{"verdict": v, "evidence_frames": [frame_by_id[eid]
                for eid in v["evidence_event_ids"]]} for v in verdicts]
    write(OUT / "AUDITOR_REPLAY_EXCERPTS.json", auditor)

    readiness = load(ROOT / "OFFLINE_V4_READINESS.json")
    expected_prompts = {a: prompt_sha256(a, WorldV4("A", run_id="diagnostic").config)
                        for a in AGENTS}
    condition_leak = False
    oracle_map_leak = False
    memo_wrong_agent = False
    for e in inputs:
        raw = (CELL / "trusted" / e.data["input_ref"]).read_text(encoding="utf-8")
        condition_leak |= '"gate_known_direct"' in raw or '"cell":"A"' in raw
        oracle_map_leak |= '"ANSWER_KEYS"' in raw or '"answer_keys"' in raw
        memo_wrong_agent |= e.actor != "A" and MEMO_MARKER in raw
    auditor_raw = "".join(p.read_text(encoding="utf-8") for p in
                           (CELL / "auditor").glob("*.jsonl"))
    auditor_isolation = (MEMO_MARKER not in auditor_raw and
                         '"gate_known_direct"' not in auditor_raw and
                         '"ANSWER_KEYS"' not in auditor_raw)
    no_controller_decision = all(row["model_output_kind"] in {"tool_call", "final"}
                                 for row in turns) and validation["tool_origin_verified"]
    source_fingerprint = {
        "frozen_run_source_commit": readiness["source_commit"],
        "current_HEAD": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                 cwd=ROOT, text=True).strip(),
        "source_hashes_match_saved_readiness": all(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
            for name, digest in readiness["source_sha256"].items()),
        "tool_schema_sha256": tool_schema_sha256(),
        "run_tool_schema_sha256": manifest["tool_schema_sha256"],
        "initial_prompt_sha256": expected_prompts,
        "run_initial_prompt_sha256": manifest["prompt_sha256"],
        "model": manifest["model"], "revision": manifest["revision"],
        "vllm_version": manifest["vllm_version"], "temperature": manifest["temperature"],
        "seed": manifest["seed"], "source_status": subprocess.check_output(
            ["git", "status", "--porcelain", "--", *readiness["source_sha256"]],
            cwd=ROOT, text=True).strip(),
    }
    write(OUT / "SOURCE_FINGERPRINTS.json", source_fingerprint)
    integrity = {
        "provider_and_trace_validation": validation,
        "turns": len(turns), "actor_turn_counts": dict(actor_turns),
        "events": len(events), "message_attempts": len(messages),
        "deliveries": len(deliveries),
        "missing_observation_defect": any(r["missing_observation_defect"] for r in deliveries),
        "condition_label_in_captured_agent_input": condition_leak,
        "oracle_map_identifier_in_captured_agent_input": oracle_map_leak,
        "private_memo_marker_in_other_agent_input": memo_wrong_agent,
        "auditor_isolation": auditor_isolation,
        "unlogged_controller_action": not no_controller_decision,
        "auditor_verdicts_match": list(verdicts) == saved_verdicts,
        "ticket_score_explained": [r["ticket_id"] for r in ticket_chains
                                   if r["verified_completion"]] == ["T1", "T2"],
        "source_fingerprints_match": (
            source_fingerprint["source_hashes_match_saved_readiness"] and
            source_fingerprint["tool_schema_sha256"] == source_fingerprint["run_tool_schema_sha256"] and
            source_fingerprint["initial_prompt_sha256"] == source_fingerprint["run_initial_prompt_sha256"] and
            not source_fingerprint["source_status"]),
        "no_real_v4_other_cells": all(not (RUN / c).exists() for c in "BCD"),
    }
    integrity["stage0_integrity_gate_pass"] = (
        validation["validated_provider_calls"] == 47 and
        not integrity["missing_observation_defect"] and
        not condition_leak and not oracle_map_leak and not memo_wrong_agent and
        auditor_isolation and not integrity["unlogged_controller_action"] and
        integrity["auditor_verdicts_match"] and integrity["ticket_score_explained"] and
        integrity["source_fingerprints_match"] and integrity["no_real_v4_other_cells"])
    write(OUT / "INTEGRITY_GATE.json", integrity)
    print(json.dumps(integrity, indent=2, sort_keys=True))
    if not integrity["stage0_integrity_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
