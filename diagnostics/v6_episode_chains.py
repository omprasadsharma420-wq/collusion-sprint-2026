"""Read-only V6 Cell A ticket, turn, and communication causal tables."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_v3 import ARTIFACTS
from trace_v2 import TraceV2
from world_v6 import WorldV6

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def artifact_in_input(path: Path, ticket: str) -> bool:
    request = read(path)
    for message in request["messages"]:
        if message.get("role") != "tool":
            continue
        try:
            result = json.loads(message["content"])
        except (TypeError, ValueError):
            continue
        if result.get("ticket_id") == ticket and result.get("artifact") == ARTIFACTS[ticket]:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell-root", type=Path, required=True)
    args = parser.parse_args()
    cell = args.cell_root.resolve()
    if not cell.is_relative_to(ROOT / "experiments") or cell.name not in "ABCD":
        raise ValueError("Expected a saved V6 cell")
    trace = TraceV2.read_jsonl(cell / "trusted/events_v2.jsonl")
    events = trace.events
    calls = read(cell / "trusted/tool_calls.json")
    messages = read(cell / "trusted/messages.json")
    record = read(cell / "manifest.json")
    inputs = [e for e in events if e.kind == "model_input_captured"]
    outputs = [e for e in events if e.kind == "model_output_captured"]
    assert len(inputs) == len(outputs) == record["model_calls"]
    invocations = {e.data["call_id"]: e for e in events if e.kind == "tool_invocation"}
    results = {e.data["call_id"]: e for e in events if e.kind == "tool_result"}
    tool_by_output = {}
    for call in calls:
        invocation = invocations[call["call_id"]]
        previous = [e for e in outputs if e.actor == call["actor"] and e.seq < invocation.seq]
        assert previous
        tool_by_output[previous[-1].event_id] = call
    turn_rows = []
    counts = {actor: 0 for actor in "ABCD"}
    for number, (input_event, output_event) in enumerate(zip(inputs, outputs), 1):
        actor = input_event.actor
        assert actor == output_event.actor
        counts[actor] += 1
        call = tool_by_output.get(output_event.event_id)
        turn_rows.append({"global_response": number, "actor": actor,
                          "actor_response_number": counts[actor],
                          "remaining_budget_after_response": 24 - counts[actor],
                          "model_input_event_id": input_event.event_id,
                          "model_output_event_id": output_event.event_id,
                          "tool_call_id": call["call_id"] if call else "",
                          "tool_invocation_event_id": invocations[call["call_id"]].event_id if call else "",
                          "tool_result_event_id": results[call["call_id"]].event_id if call else "",
                          "chosen_action": call["tool_name"] if call else "FINAL_TEXT",
                          "result_ok": call["result"].get("ok") if call else "",
                          "reason_code": call["result"].get("reason_code", "") if call else "",
                          "ticket_id": call["arguments"].get("ticket_id", "") if call else ""})
    assert counts == record["actor_response_counts"]
    write_csv(OUT / "V6_A_67_TURNS.csv", turn_rows)
    ticket_rows = []
    for ticket in "T1 T2 T3 T4".split():
        assignments = [e for e in events if e.kind == "task_state" and
                       e.data.get("ticket_id") == ticket and e.data.get("status") == "assigned"]
        assert len(assignments) == 1
        owner = assignments[0].data["owner"]
        reads = []
        for call in calls:
            if call["actor"] != owner or call["tool_name"] != "read_ticket_artifact" or \
                    call["arguments"]["ticket_id"] != ticket or not call["result"].get("ok"):
                continue
            result_event = results[call["call_id"]]
            next_input = next((e for e in inputs if e.actor == owner and e.seq > result_event.seq), None)
            reads.append({"call_id": call["call_id"], "tool_result_event_id": result_event.event_id,
                          "next_input_event_id": next_input.event_id if next_input else None,
                          "exact_artifact_in_next_input": artifact_in_input(
                              cell / "trusted" / next_input.data["input_ref"], ticket) if next_input else False})
        submissions = []
        for call in calls:
            if call["tool_name"] != "submit_work" or call["arguments"]["ticket_id"] != ticket:
                continue
            submissions.append({"call_id": call["call_id"], "actor": call["actor"],
                                "evidence_event_id": call["result"].get("evidence_event_id"),
                                "findings": call["arguments"]["findings"],
                                "accepted": call["result"].get("ok"),
                                "feedback_code": call["result"].get("reason_code"),
                                "value_mismatch_keys": call["result"].get("value_mismatch_keys", [])})
        declared = [e.event_id for e in events if e.kind == "task_state" and
                    e.data.get("ticket_id") == ticket and e.data.get("status") == "analysis_declared"]
        ticket_rows.append({"ticket_id": ticket, "owner": owner,
                            "assignment_event_id": assignments[0].event_id,
                            "owner_artifact_reads": reads, "submissions": submissions,
                            "declaration_event_ids": declared,
                            "verified_completion": ticket in record["outcome"]["valid_ticket_analyses"]})
    (OUT / "V6_A_TICKET_CHAINS.json").write_text(json.dumps(ticket_rows, indent=2) + "\n", encoding="utf-8")
    causal = []
    for message_id, message in messages.items():
        attempt = next(e for e in events if e.kind == "attempt" and e.data["message_id"] == message_id)
        accepted = next((e for e in events if e.kind == "accepted_write" and e.data["message_id"] == message_id), None)
        for recipient in message["recipients"]:
            delivery = next((e for e in events if e.kind == "recipient_delivery"
                             and e.data["message_id"] == message_id and e.data["recipient"] == recipient), None)
            reads = [e for e in events if e.kind == "resource_read" and e.actor == recipient
                     and delivery and e.seq > delivery.seq and message_id in e.data.get("message_ids", [])]
            inclusions = [e for e in inputs if e.actor == recipient and delivery and e.seq > delivery.seq
                          and WorldV6._visible_messages(read(cell / "trusted" / e.data["input_ref"])["messages"])
                          .get(message_id) == message["body"]]
            observations = [e for e in events if e.kind == "recipient_observation"
                            and e.actor == recipient and e.data["message_id"] == message_id]
            assert bool(observations) == bool(inclusions)
            causal.append({"message_id": message_id, "route": message["route"],
                           "sender": message["actor"], "recipient": recipient,
                           "payload_digest": message["payload_digest"],
                           "attempt_event_id": attempt.event_id,
                           "accepted_write_event_id": accepted.event_id if accepted else "",
                           "delivery_event_id": delivery.event_id if delivery else "",
                           "resource_read_event_ids": ";".join(e.event_id for e in reads),
                           "first_body_in_model_input_event_id": inclusions[0].event_id if inclusions else "",
                           "unique_observation_event_ids": ";".join(e.event_id for e in observations),
                           "policy_content_label": "PENDING_INDEPENDENT_HUMAN_REVIEW"})
    write_csv(OUT / "V6_A_MESSAGE_CAUSAL_PATHS.csv", causal)
    print(json.dumps({"turn_rows": len(turn_rows), "tickets": len(ticket_rows),
                      "addressed_paths": len(causal),
                      "observed_paths": sum(bool(x["unique_observation_event_ids"]) for x in causal)}, indent=2))


if __name__ == "__main__":
    main()
