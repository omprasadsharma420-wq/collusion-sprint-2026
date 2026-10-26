"""Offline-only reconstruction of the preserved v5 real Cell A episode."""

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
from protocol_v3 import AGENTS, ARTIFACTS, MEMO_MARKER
from protocol_v5 import CellConfig, prompt_sha256, tool_schema_sha256
from run_real_modal_v5 import validate_cell
from trace_v2 import TraceV2

RUN = ROOT / "experiments/real_v5_longer_horizon_20261025T164017Z"
CELL = RUN / "A"
OUT = ROOT / "researcher_analysis_20261025_v5"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def csv_write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tool_body_in_request(request: dict, message_id: str, body: str) -> bool:
    for item in request["messages"]:
        if item.get("role") != "tool":
            continue
        try:
            result = json.loads(item["content"])
        except (ValueError, KeyError):
            continue
        if any(x.get("message_id") == message_id and x.get("body") == body
               for x in result.get("items", [])):
            return True
    return False


def summary_of_input(request: dict) -> str:
    if len(request["messages"]) <= 2:
        return "initial system/user briefing"
    last = request["messages"][-1]
    if last.get("role") != "tool":
        return f"last_role={last.get('role')}; messages={len(request['messages'])}"
    try:
        result = json.loads(last["content"])
    except (ValueError, KeyError):
        return f"last_tool={last.get('name')}; non-JSON result"
    ids = [x.get("message_id") for x in result.get("items", [])]
    return (f"last_tool={last.get('name')}; ok={result.get('ok')}; "
            f"ticket={result.get('ticket_id')}; message_ids={','.join(ids)}; "
            f"messages={len(request['messages'])}")


def redact_arguments(arguments: dict) -> str:
    redacted = dict(arguments)
    for key in ("message", "entry"):
        if key in redacted:
            redacted[key] = "SHA256:" + hashlib.sha256(
                redacted[key].encode("utf-8")).hexdigest()
    if "findings" in redacted:
        redacted["findings"] = [x["key"] for x in redacted["findings"]]
    return json.dumps(redacted, sort_keys=True, ensure_ascii=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trace = TraceV2.read_jsonl(CELL / "trusted/events_v2.jsonl")
    trace.validate()
    events = list(trace.events)
    inputs = [e for e in events if e.kind == "model_input_captured"]
    outputs = [e for e in events if e.kind == "model_output_captured"]
    tools = load(CELL / "trusted/tool_calls.json")
    evidence = load(CELL / "trusted/evidence.json")
    messages = load(CELL / "trusted/messages.json")
    outcome = load(CELL / "trusted/outcome.json")
    manifest = load(CELL / "manifest.json")
    decision = load(RUN / "V5_LIVE_DECISION.json")
    validation = validate_cell(RUN, "A", manifest, provider_start=1, provider_stop=58)
    assert len(inputs) == len(outputs) == manifest["model_calls"] == 58
    assert len(events) == 277 and outcome["task_score"] == 2
    assert not any((RUN / c).exists() for c in "BCD")
    by_call = {x["call_id"]: x for x in tools}
    invocations = {e.data["call_id"]: e for e in events if e.kind == "tool_invocation"}
    results = {e.data["call_id"]: e for e in events if e.kind == "tool_result"}
    actor_counts = Counter()
    turns: list[dict] = []
    for i, (inp, out) in enumerate(zip(inputs, outputs), 1):
        assert inp.actor == out.actor
        actor_counts[inp.actor] += 1
        next_seq = inputs[i].seq if i < len(inputs) else len(events) + 1
        within = [e for e in events if out.seq < e.seq < next_seq]
        inv = [e for e in within if e.kind == "tool_invocation"]
        assert len(inv) <= 1
        call = by_call[inv[0].data["call_id"]] if inv else None
        result = call["result"] if call else {}
        state = [f"{e.event_id}:{e.kind}:{e.data.get('ticket_id', '')}:"
                 f"{e.data.get('status', e.data.get('accepted', ''))}"
                 for e in within if e.kind in {"task_state", "evidence_verified", "supervisor_decision"}]
        request = load(CELL / "trusted" / inp.data["input_ref"])
        turns.append({
            "provider_call": i, "actor": inp.actor, "actor_response_number": actor_counts[inp.actor],
            "remaining_response_budget_after_call": 24 - actor_counts[inp.actor],
            "model_input_event_id": inp.event_id, "model_output_event_id": out.event_id,
            "prior_visible_input_summary": summary_of_input(request),
            "tool_call_id": call["call_id"] if call else "",
            "tool_invocation_event_id": inv[0].event_id if inv else "",
            "tool_result_event_id": results[call["call_id"]].event_id if call else "",
            "chosen_action": call["tool_name"] if call else "FINAL_TEXT",
            "arguments_redacted": redact_arguments(call["arguments"]) if call else "",
            "result_ok": result.get("ok", "") if call else "",
            "result_status": result.get("status", "final") if call else "final",
            "result_reason": result.get("reason_code", result.get("reason", "")) if call else "",
            "ticket_state_changes": ";".join(state),
        })
    csv_write(OUT / "V5_A_58_TURNS.csv", turns)

    tickets = []
    for ticket in "T1", "T2", "T3", "T4":
        claims = [x for x in tools if x["tool_name"] == "assign_ticket"
                  and x["arguments"].get("ticket_id") == ticket]
        accepted_claims = [x for x in claims if x["result"]["ok"]]
        assert len(accepted_claims) == 1
        owner = accepted_claims[0]["actor"]
        reads = []
        for call in tools:
            if call["tool_name"] != "read_ticket_artifact" or call["actor"] != owner or \
                    call["arguments"]["ticket_id"] != ticket or not call["result"]["ok"]:
                continue
            result_event = results[call["call_id"]]
            nxt = next((e for e in inputs if e.actor == owner and e.seq > result_event.seq), None)
            included = False
            if nxt:
                request = load(CELL / "trusted" / nxt.data["input_ref"])
                for item in request["messages"]:
                    if item.get("role") != "tool":
                        continue
                    try:
                        result = json.loads(item["content"])
                    except (ValueError, KeyError):
                        continue
                    included |= (result.get("ticket_id") == ticket and
                                 result.get("artifact") == ARTIFACTS[ticket])
            reads.append({"tool_call_id": call["call_id"],
                          "tool_result_event_id": result_event.event_id,
                          "next_owner_input_event_id": nxt.event_id if nxt else None,
                          "exact_artifact_in_next_input": included})
        submissions = []
        for call in tools:
            if call["tool_name"] != "submit_work" or call["arguments"]["ticket_id"] != ticket:
                continue
            ev = next(e for e in evidence if e["event_id"] == call["result"]["evidence_event_id"])
            submissions.append({"tool_call_id": call["call_id"],
                                "evidence_event_id": ev["event_id"],
                                "readiness_submitted": ev["normalized"].get("readiness") if ev["normalized"] else None,
                                "feedback_code": call["result"].get("reason_code"),
                                "mismatch_keys": call["result"].get("value_mismatch_keys", []),
                                "verifier_accepted": ev["accepted"]})
        closed = [e.event_id for e in events if e.kind == "task_state"
                  and e.data.get("ticket_id") == ticket and
                  e.data.get("status") == "analysis_declared"]
        tickets.append({
            "ticket_id": ticket, "eligible_at_initial_state": True,
            "attempted_claim_call_ids": [x["call_id"] for x in claims],
            "owner": owner, "accepted_claim_call_id": accepted_claims[0]["call_id"],
            "assignment_event_id": next(e.event_id for e in events
                if e.kind == "task_state" and e.data.get("ticket_id") == ticket
                and e.data.get("status") == "assigned"),
            "artifact_reads": reads, "submissions": submissions,
            "declare_complete_event_ids": closed,
            "verified_completion": ticket in outcome["valid_ticket_analyses"],
        })
    write(OUT / "V5_TICKET_CHAINS.json", tickets)

    communication = []
    for mid, message in messages.items():
        attempt = next(e for e in events if e.kind == "attempt" and e.data["message_id"] == mid)
        accepted = next(e for e in events if e.kind == "accepted_write" and e.data["message_id"] == mid)
        for recipient in message["recipients"]:
            delivered = next(e for e in events if e.kind == "recipient_delivery"
                             and e.data["message_id"] == mid and e.data["recipient"] == recipient)
            reads = [e for e in events if e.kind == "resource_read" and e.actor == recipient
                     and e.seq > delivered.seq and e.data["resource_id"] == message["route"]
                     and (message["route"] != "release_checklist" or
                          e.data.get("ticket_id") == message.get("ticket_id"))]
            returned = [e for e in reads if mid in e.data["message_ids"]]
            inclusions = [e for e in inputs if e.actor == recipient and e.seq > delivered.seq
                          and tool_body_in_request(load(CELL / "trusted" / e.data["input_ref"]),
                                                   mid, message["body"])]
            observations = [e for e in events if e.kind == "recipient_observation"
                            and e.actor == recipient and e.data["message_id"] == mid]
            communication.append({
                "message_id": mid, "route": message["route"], "sender": message["actor"],
                "recipient": recipient, "payload_digest": message["payload_digest"],
                "attempt_event_id": attempt.event_id, "accepted_event_id": accepted.event_id,
                "delivery_event_id": delivered.event_id,
                "matching_resource_read_event_ids": ";".join(e.event_id for e in reads),
                "returned_body_read_event_ids": ";".join(e.event_id for e in returned),
                "first_exact_input_inclusion_event_id": inclusions[0].event_id if inclusions else "",
                "unique_observation_event_ids": ";".join(e.event_id for e in observations),
                "missing_observation_defect": bool(inclusions) and not observations,
            })
    csv_write(OUT / "V5_COMMUNICATION_CAUSAL_CHAIN.csv", communication)

    pooled = project(trace, AuditView.POOLED_METADATA)
    replay = list(run_audit(pooled))
    saved = [json.loads(x) for x in
             (CELL / "auditor/verdicts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert replay == saved
    write(OUT / "V5_AUDITOR_REPLAY.json", {
        "rule_source": "audit_rules_v3.py", "projection": "pooled_metadata",
        "frame_count": len(pooled), "replayed_verdicts": replay,
        "saved_verdicts_exact_match": True,
    })

    readiness = load(ROOT / "OFFLINE_V5_READINESS.json")
    source_hashes_match = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                              for name, digest in readiness["source_sha256"].items())
    prompt_match = manifest["prompt_sha256"] == {
        actor: prompt_sha256(actor, CellConfig.for_cell("A")) for actor in AGENTS}
    tool_match = manifest["tool_schema_sha256"] == tool_schema_sha256()
    no_labels_in_agent_inputs = True
    no_memo_in_other_agent_inputs = True
    no_oracle_sidecars_in_agent_inputs = True
    for event in inputs:
        raw = (CELL / "trusted" / event.data["input_ref"]).read_text(encoding="utf-8")
        no_labels_in_agent_inputs &= ('"gate_known_direct"' not in raw and '"cell":"A"' not in raw)
        no_memo_in_other_agent_inputs &= event.actor == "A" or MEMO_MARKER not in raw
        no_oracle_sidecars_in_agent_inputs &= ('"ANSWER_KEYS"' not in raw and
                                                '"researcher_only_setup"' not in raw and
                                                '"ground_truth"' not in raw)
    audit_text = "".join(path.read_text(encoding="utf-8") for path in
                         (CELL / "auditor").glob("*.jsonl"))
    auditor_privacy = all(x not in audit_text for x in (
        MEMO_MARKER, '"gate_known_direct"', '"ANSWER_KEYS"', '"ground_truth"'))
    receipts = sorted((RUN / "trusted_provider_calls").glob("*/receipt.json"))
    response_ids = [load(path)["response_id"] for path in receipts]
    status = subprocess.check_output(["git", "status", "--porcelain", "--",
        *readiness["source_sha256"]], cwd=ROOT, text=True).strip()
    gate = {
        "current_git_HEAD": subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip(),
        "run_source_commit": manifest["source_commit"],
        "run_status": manifest["status"],
        "total_responses": len(inputs), "per_agent_responses": dict(actor_counts),
        "last_call": {"actor": turns[-1]["actor"], "actor_response_number":
                      turns[-1]["actor_response_number"], "output_event_id":
                      turns[-1]["model_output_event_id"]},
        "provider_receipts": len(receipts), "unique_provider_response_ids": len(set(response_ids)),
        "event_count": len(events), "event_chain_tip_sha256": events[-1].hash,
        "replayed_auditor_verdicts": len(replay),
        "verified_score": len([x for x in tickets if x["verified_completion"]]),
        "message_attempts": len(messages), "addressable_deliveries": len(communication),
        "unique_observation_events": sum(e.kind == "recipient_observation" for e in events),
        "missing_observation_defect": any(x["missing_observation_defect"] for x in communication),
        "source_hashes_match_readiness": source_hashes_match,
        "source_tree_clean_for_scientific_files": not status,
        "prompt_hashes_match": prompt_match, "tool_schema_hash_matches": tool_match,
        "agent_inputs_without_condition_labels": no_labels_in_agent_inputs,
        "private_memo_not_in_other_agent_inputs": no_memo_in_other_agent_inputs,
        "agent_inputs_without_oracle_sidecars": no_oracle_sidecars_in_agent_inputs,
        "auditor_projection_privacy": auditor_privacy,
        "saved_replay_agrees": replay == saved,
        "bcd_not_run": all(not (RUN / c).exists() for c in "BCD"),
        "prior_saved_validation": validation,
    }
    gate["offline_integrity_pass"] = (
        len(receipts) == len(set(response_ids)) == len(inputs) == 58 and
        gate["verified_score"] == 2 and not gate["missing_observation_defect"] and
        source_hashes_match and not status and prompt_match and tool_match and
        no_labels_in_agent_inputs and no_memo_in_other_agent_inputs and
        no_oracle_sidecars_in_agent_inputs and auditor_privacy and replay == saved and
        gate["bcd_not_run"] and decision["pilot_pass"] is False)
    write(OUT / "V5_OFFLINE_INTEGRITY.json", gate)
    print(json.dumps(gate, indent=2, sort_keys=True))
    if not gate["offline_integrity_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
