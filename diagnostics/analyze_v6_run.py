"""Read-only evidence summary of one saved bounded V6 real-model run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_rules_v3 import run_audit
from trace_v2 import TraceV2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    run = args.run_root.resolve()
    if not run.is_relative_to(ROOT / "experiments") or not run.name.startswith("real_v6_verifier_usability_"):
        raise ValueError("Expected saved V6 experiment folder")
    decision = read(run / "V6_LIVE_DECISION.json")
    manifest = read(run / "run_manifest.json")
    validation = read(run / "VALIDATION.json")
    readiness = read(OUT / "OFFLINE_V6_READINESS.json")
    assert manifest["source_commit"] == validation["source_commit"] == readiness["source_commit"]
    provider_folders = sorted((run / "trusted_provider_calls").glob("[0-9]*_*")) if (run / "trusted_provider_calls").exists() else []
    receipts = [read(folder / "receipt.json") for folder in provider_folders]
    assert len(receipts) == validation["model_calls"]
    assert len([r for r in receipts if r.get("status") == 200 and r.get("response_id")]) == len(receipts)
    assert len({r["response_id"] for r in receipts}) == len(receipts)
    by_cell = {}
    obs_rows = []
    verdict_rows = []
    offset = 0
    for cell in "ABCD":
        cell_root = run / cell
        if not cell_root.exists():
            by_cell[cell] = {"status": "NOT_RUN"}
            continue
        record = read(cell_root / "manifest.json")
        check = read(cell_root / "VALIDATION.json")
        trace = TraceV2.read_jsonl(cell_root / "trusted/events_v2.jsonl")
        events = trace.events
        tools = read(cell_root / "trusted/tool_calls.json")
        messages = read(cell_root / "trusted/messages.json")
        inputs = [e for e in events if e.kind == "model_input_captured"]
        local_receipts = receipts[offset:offset + record["model_calls"]]
        offset += record["model_calls"]
        assert len(inputs) == len(local_receipts)
        input_by_ref = {e.data["input_ref"]: (e, local_receipts[index])
                        for index, e in enumerate(inputs)}
        pooled = tuple(jsonl(cell_root / "auditor/pooled_metadata.jsonl"))
        saved = tuple(jsonl(cell_root / "auditor/verdicts.jsonl"))
        assert run_audit(pooled) == saved
        for verdict in saved:
            verdict_rows.append({"cell": cell, "rule": verdict["rule_id"],
                                 "decision_seq": verdict["decision_seq"],
                                 "verdict": verdict["verdict"],
                                 "basis_event_ids": ";".join(verdict["evidence_event_ids"]),
                                 "ground_truth_status": "UNKNOWN_PENDING_INDEPENDENT_CONTENT_REVIEW"})
        if not saved:
            verdict_rows.append({"cell": cell, "rule": "R1/R2", "decision_seq": "",
                                 "verdict": "NOT_EVALUATED_NO_CANDIDATE_FRAME", "basis_event_ids": "",
                                 "ground_truth_status": "UNKNOWN_PENDING_INDEPENDENT_CONTENT_REVIEW"})
        for event in events:
            if event.kind != "recipient_observation":
                continue
            ref = event.data["model_input_ref"]
            input_event, receipt = input_by_ref[ref]
            msg = messages[event.data["message_id"]]
            raw = read(cell_root / "trusted" / ref)
            visible = __import__("world_v6").WorldV6._visible_messages(raw["messages"])
            assert visible.get(event.data["message_id"]) == msg["body"]
            provider_request = (provider_folders[receipt["call_number"] - 1] / "request.json").read_bytes()
            assert hashlib.sha256(provider_request).hexdigest() == receipt["request_sha256"]
            obs_rows.append({"cell": cell, "observation_event_id": event.event_id,
                             "message_id": event.data["message_id"], "sender": msg["actor"],
                             "recipient": event.actor, "route": msg["route"],
                             "payload_digest": event.data["payload_digest"],
                             "model_input_event_id": input_event.event_id,
                             "model_input_ref": ref, "provider_call_number": receipt["call_number"],
                             "provider_response_id": receipt["response_id"],
                             "content_policy_label": "PENDING_INDEPENDENT_HUMAN_REVIEW"})
        count = lambda kind: sum(e.kind == kind for e in events)
        by_cell[cell] = {
            "status": record["status"], "validation_ok": check.get("validation_ok", False),
            "task_score": record["outcome"]["task_score"],
            "valid_ticket_analyses": record["outcome"]["valid_ticket_analyses"],
            "accepted_t4_by_b": check.get("accepted_t4_by_b", False),
            "responses": record["model_calls"], "per_agent_responses": record["actor_response_counts"],
            "tool_actions": len(tools), "attempts": count("attempt"),
            "accepted_writes": count("accepted_write"),
            "denied_writes": count("authorization_denial"),
            "addressed_deliveries": count("recipient_delivery"),
            "recipient_input_observations": count("recipient_observation"),
            "agent_reports": count("agent_discovery_report"),
            "auditor_candidate_decisions": len(saved),
            "auditor_alerts": sum(v["verdict"] == "alert" for v in saved),
            "event_count": len(events),
            "event_chain_tip_sha256": events[-1].hash if events else None,
            "human_content_review": "PENDING",
        }
    assert offset == len(receipts)
    summary = {"provenance": "REAL MODEL EPISODE", "run_root": str(run.relative_to(ROOT)),
               "source_commit": manifest["source_commit"],
               "provider": {"model": manifest["model"], "revision": manifest["revision"],
                            "vllm_version": manifest["vllm_version"]},
               "total_real_model_responses": len(receipts), "cells": by_cell,
               "pilot_pass": decision["pilot_pass"], "decision": decision,
               "offline_integrity_pass": all(v.get("validation_ok", True) for v in by_cell.values()),
               "content_labels_completed": 0}
    OUT.mkdir(exist_ok=True)
    (OUT / "V6_REAL_RESULTS.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(OUT / "V6_OBSERVATION_PROVENANCE.csv", obs_rows,
              ["cell", "observation_event_id", "message_id", "sender", "recipient", "route",
               "payload_digest", "model_input_event_id", "model_input_ref", "provider_call_number",
               "provider_response_id", "content_policy_label"])
    write_csv(OUT / "V6_AUDITOR_REPLAY.csv", verdict_rows,
              ["cell", "rule", "decision_seq", "verdict", "basis_event_ids", "ground_truth_status"])
    print(json.dumps({"cells": {k: v.get("status") for k, v in by_cell.items()},
                      "responses": len(receipts), "observations": len(obs_rows),
                      "pilot_pass": decision["pilot_pass"]}, indent=2))


if __name__ == "__main__":
    main()
