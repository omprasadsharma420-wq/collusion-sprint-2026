"""Read-only extraction of every preserved v3/v4/v5 failed submit_work call.

This is researcher-only mechanical extraction. It does not assign human semantic labels.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_v3 import ANSWER_KEYS, ARTIFACTS
from trace_v2 import TraceV2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"
RUNS = [
    *( ("V3", cell, ROOT / "experiments/real_qwen3_8b_modal_20261025T144820Z" / cell) for cell in "ABCD"),
    ("V4", "A", ROOT / "experiments/real_v4_schema_visible_20261025T160532Z/A"),
    ("V5", "A", ROOT / "experiments/real_v5_longer_horizon_20261025T164017Z/A"),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []
    for version, cell, root in RUNS:
        calls = json.loads((root / "trusted/tool_calls.json").read_text(encoding="utf-8"))
        trace = TraceV2.read_jsonl(root / "trusted/events_v2.jsonl")
        inputs = [event for event in trace.events if event.kind == "model_input_captured"]
        invocations = {event.data["call_id"]: event for event in trace.events if event.kind == "tool_invocation"}
        for call in calls:
            if call["tool_name"] != "submit_work" or call["result"].get("ok"):
                continue
            ticket = call["arguments"]["ticket_id"]
            invocation = invocations[call["call_id"]]
            earlier = [event for event in inputs if event.actor == call["actor"] and event.seq < invocation.seq]
            assert earlier, (version, cell, call["call_id"])
            preceding = earlier[-1]
            raw = (root / "trusted" / preceding.data["input_ref"]).read_text(encoding="utf-8")
            request = json.loads(raw)
            artifact_seen = False
            for message in request["messages"]:
                if message.get("role") != "tool":
                    continue
                try:
                    result = json.loads(message["content"])
                except (TypeError, ValueError):
                    continue
                artifact_seen |= result.get("artifact") == ARTIFACTS[ticket]
            rows.append({
                "version": version,
                "cell": cell,
                "actor": call["actor"],
                "call_id": call["call_id"],
                "invocation_event_id": invocation.event_id,
                "evidence_event_id": call["result"].get("evidence_event_id", ""),
                "ticket_id": ticket,
                "model_input_event_id": preceding.event_id,
                "model_input_ref": preceding.data["input_ref"],
                "artifact_exact_text_in_input": str(artifact_seen).lower(),
                "submitted_findings_json": json.dumps(call["arguments"]["findings"], ensure_ascii=False, sort_keys=True),
                "server_feedback_json": json.dumps(call["result"], ensure_ascii=False, sort_keys=True),
                "expected_values_json_RESEARCHER_ONLY": json.dumps(ANSWER_KEYS[ticket], ensure_ascii=False, sort_keys=True),
                "semantic_correctness_human_review": "PENDING_INDEPENDENT_HUMAN_REVIEW",
            })
    assert len(rows) == 38, len(rows)
    path = OUT / "researcher_only/FAILED_SUBMIT_WORK_V3_V4_V5.csv"
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Extracted {len(rows)} failed submissions to {path}")


if __name__ == "__main__":
    main()
