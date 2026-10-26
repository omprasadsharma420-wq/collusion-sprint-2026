"""Build an unlabeled combined attempted-message packet after a saved V6 run.

Only the blind CSV and rubric go to an annotator. Linkage remains researcher-only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_v3 import MEMO_MARKER
from trace_v2 import TraceV2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"
OLD = ROOT / "researcher_analysis_20261025_v5"
PSEUDONYM = {"A": "Worker P", "B": "Worker Q", "C": "Worker R", "D": "Worker S"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root.resolve()
    if not run.is_relative_to(ROOT / "experiments") or not run.name.startswith("real_v6_verifier_usability_"):
        raise ValueError("Expected one saved V6 real run under experiments")
    old = read_csv(OLD / "blind/MASTER_BLIND_MESSAGE_REVIEW.csv")
    prior_map = {row["row_id"]: row for row in read_csv(OLD / "researcher_only/MASTER_ROW_LINKAGE.csv")}
    assert len(old) == len(prior_map) == 22
    combined = []
    for row in old:
        source = prior_map[row["row_id"]]
        combined.append(({
            "attempted_route": row["attempted_route"],
            "sender_pseudonym": row["sender_pseudonym"],
            "intended_audience": row["intended_audience"],
            "prior_context": row["prior_context"],
            "message_text": row["message_text"],
        }, {"cohort": source["cohort"], "cell": source.get("source_episode_code", ""),
            "source_path": source["source_path"], "source_review_id": source["source_review_id"],
            "source_event_id": source["source_event_id"], "source_message_id": "",
            "accepted_event_id": "", "delivery_event_ids": "", "observation_event_ids": "",
            "source_message_sha256": source["message_sha256"]}))
    v6_count = 0
    for cell in "ABCD":
        cell_root = run / cell
        if not cell_root.exists():
            continue
        messages = json.loads((cell_root / "trusted/messages.json").read_text(encoding="utf-8"))
        trace = TraceV2.read_jsonl(cell_root / "trusted/events_v2.jsonl")
        calls = json.loads((cell_root / "trusted/tool_calls.json").read_text(encoding="utf-8"))
        events = trace.events
        invocations = [e for e in events if e.kind == "tool_invocation"]
        for message_id, message in messages.items():
            attempt = next(e for e in events if e.kind == "attempt" and e.data["message_id"] == message_id)
            own_prior = [e for e in invocations if e.actor == message["actor"] and e.seq < attempt.seq]
            prior_call = None
            if len(own_prior) >= 2:
                id_ = own_prior[-2].data["call_id"]
                prior_call = next((c for c in calls if c["call_id"] == id_), None)
            context = (f"Previous own tool: {prior_call['tool_name']} returned "
                       f"{prior_call['result'].get('reason_code', prior_call['result'].get('status', 'ok'))}."
                       if prior_call else "No prior own-tool context available in source extract.")
            text = message["body"].replace(MEMO_MARKER, "[REDACTED_PRIVATE_MEMO_IDENTIFIER]")
            blind = {"attempted_route": message["route"],
                     "sender_pseudonym": PSEUDONYM[message["actor"]],
                     "intended_audience": "; ".join(PSEUDONYM[r] for r in message["recipients"]),
                     "prior_context": context, "message_text": text}
            accepted = [e.event_id for e in events if e.kind == "accepted_write" and e.data["message_id"] == message_id]
            delivered = [e.event_id for e in events if e.kind == "recipient_delivery" and e.data["message_id"] == message_id]
            observed = [e.event_id for e in events if e.kind == "recipient_observation" and e.data["message_id"] == message_id]
            privileged = {"cohort": "V6_REAL_MODEL_EPISODE", "cell": cell,
                          "source_path": str(cell_root.relative_to(ROOT)), "source_review_id": "",
                          "source_event_id": attempt.event_id, "source_message_id": message_id,
                          "accepted_event_id": ";".join(accepted),
                          "delivery_event_ids": ";".join(delivered),
                          "observation_event_ids": ";".join(observed),
                          "source_message_sha256": hashlib.sha256(message["body"].encode()).hexdigest()}
            combined.append((blind, privileged))
            v6_count += 1
    random.Random(4266).shuffle(combined)
    packet = []
    linkage = []
    for number, (blind, privileged) in enumerate(combined, 1):
        row_id = f"CBS-V6-{number:03d}"
        packet.append({"row_id": row_id, **blind, "category": "", "rule_violated": "",
                       "evidence_excerpt": "", "confidence_or_uncertain": "",
                       "annotation_notes": ""})
        linkage.append({"row_id": row_id, **privileged})
    assert len(packet) == len(linkage) == 22 + v6_count
    assert all(not any(row[key] for key in ("category", "rule_violated", "evidence_excerpt",
                                           "confidence_or_uncertain", "annotation_notes")) for row in packet)
    write_csv(OUT / "blind/MASTER_BLIND_MESSAGE_REVIEW_V3_TO_V6.csv", packet)
    write_csv(OUT / "researcher_only/MASTER_ROW_LINKAGE_V3_TO_V6.csv", linkage)
    (OUT / "researcher_only/BLIND_PACKET_COUNTS.json").write_text(json.dumps({
        "old_attempts": 22, "v6_attempts": v6_count, "combined_attempts": len(packet),
        "independent_human_labels_completed": 0,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(packet)} unannotated attempted-message rows; V6={v6_count}.")


if __name__ == "__main__":
    main()
