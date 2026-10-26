"""Offline-only assembly of blinded text rows and frozen auditor decisions."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_rules_v3 import run_audit
from run_mock_v3 import run as run_mock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261025_v5"
EXP = ROOT / "experiments"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_jsonl(path: Path) -> tuple[dict, ...]:
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def prepare_blind() -> None:
    specs = [
        ("V3", EXP / "real_qwen3_8b_modal_20261025T144820Z/researcher/forensic_review/BLIND_MESSAGE_REVIEW.csv", 14),
        ("V4", EXP / "real_v4_schema_visible_20261025T160532Z/researcher/blind_review_v4/BLIND_MESSAGE_REVIEW_V4.csv", 4),
        ("V5", EXP / "real_v5_longer_horizon_20261025T164017Z/researcher/blind_review_v5/BLIND_MESSAGE_REVIEW_V5.csv", 4),
    ]
    originals = []
    for cohort, path, expected in specs:
        records = read_csv(path)
        assert len(records) == expected, (cohort, len(records))
        for source in records:
            assert not any(source.get(key, "").strip() for key in ("authorized", "unauthorized_confidential", "joint_plan_evidence"))
            originals.append((cohort, path, source))
    random.Random(4187).shuffle(originals)
    blind, linkage = [], []
    for number, (cohort, path, source) in enumerate(originals, 1):
        row_id = f"CBS-{number:03d}"
        context = source.get("prior_context") or source.get("minimal_prior_context") or "No prior context supplied in source extract."
        message = source["message_text_actor_ids_pseudonymized"]
        blind.append({
            "row_id": row_id,
            "attempted_route": source["attempted_route"],
            "sender_pseudonym": source["sender"],
            "intended_audience": source["intended_audience"],
            "prior_context": context,
            "message_text": message,
            "category": "",
            "rule_violated": "",
            "evidence_excerpt": "",
            "confidence_or_uncertain": "",
            "annotation_notes": "",
        })
        linkage.append({
            "row_id": row_id,
            "cohort": cohort,
            "source_path": str(path.relative_to(ROOT)),
            "source_review_id": source["review_id"],
            "source_event_id": source.get("event_id", ""),
            "source_episode_code": source.get("episode_code", ""),
            "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        })
    assert len(blind) == len({row["row_id"] for row in blind}) == 22
    write_csv(OUT / "blind/MASTER_BLIND_MESSAGE_REVIEW.csv", blind, list(blind[0]))
    write_csv(OUT / "researcher_only/MASTER_ROW_LINKAGE.csv", linkage, list(linkage[0]))


def replay_auditors() -> None:
    runs = [
        *( (f"V3-{cell}", EXP / "real_qwen3_8b_modal_20261025T144820Z" / cell, "REAL MODEL EPISODE") for cell in "ABCD"),
        ("V4-A", EXP / "real_v4_schema_visible_20261025T160532Z/A", "REAL MODEL EPISODE"),
        ("V5-A", EXP / "real_v5_longer_horizon_20261025T164017Z/A", "REAL MODEL EPISODE"),
        ("V5-valid-HOLD", EXP / "v5_longer_horizon_offline_fixture/valid_hold", "SCRIPTED SOFTWARE FIXTURE"),
        ("V5-invalid-READY", EXP / "v5_longer_horizon_offline_fixture/invalid_ready", "SCRIPTED SOFTWARE FIXTURE"),
    ]
    mock_root = OUT / "scripted_benign_v3_mock"
    run_mock(mock_root, cell="D")
    runs.append(("V3-benign-mock", mock_root, "SCRIPTED SOFTWARE FIXTURE"))
    decisions = []
    summaries = []
    for run_id, root, cohort_type in runs:
        projection_path = root / "auditor/projections/pooled_metadata.jsonl"
        if not projection_path.exists():
            projection_path = root / "auditor/pooled_metadata.jsonl"
        frames = read_jsonl(projection_path)
        actual = run_audit(frames)
        saved = read_jsonl(root / "auditor/verdicts.jsonl")
        assert actual == saved, (run_id, actual, saved)
        summaries.append({"run_id": run_id, "cohort_type": cohort_type, "projection_frames": len(frames),
                          "saved_replay_exact_match": True, "decision_count": len(actual)})
        for d in actual:
            known = "KNOWN_SCRIPTED_INVALID_RELEASE" if run_id == "V5-invalid-READY" else (
                "KNOWN_SCRIPTED_BENIGN_COOPERATION" if run_id == "V3-benign-mock" else (
                "KNOWN_SCRIPTED_VALID_HOLD" if run_id == "V5-valid-HOLD" else "UNKNOWN_PENDING_INDEPENDENT_CODING"))
            decisions.append({
                "run_id": run_id,
                "monitor_rule": d["rule_id"],
                "decision_seq": str(d["decision_seq"]),
                "verdict": d["verdict"],
                "basis_event_ids": ";".join(d["evidence_event_ids"]),
                "ground_truth_status": known,
                "inferred_candidate_type": "checklist_write_R1_evaluated" if d["rule_id"] == "R1" else "release_approval_R2_evaluated",
                "cohort_type": cohort_type,
            })
        if not actual:
            decisions.append({"run_id": run_id, "monitor_rule": "R1/R2", "decision_seq": "", "verdict": "NOT_EVALUATED_NO_CANDIDATE_FRAME",
                              "basis_event_ids": "", "ground_truth_status": "KNOWN_SCRIPTED_VALID_HOLD" if run_id == "V5-valid-HOLD" else "UNKNOWN_PENDING_INDEPENDENT_CODING",
                              "inferred_candidate_type": "none", "cohort_type": cohort_type})
    write_csv(OUT / "AUDITOR_DECISIONS.csv", decisions, list(decisions[0]))
    (OUT / "AUDITOR_REPLAY_SUMMARY.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    prepare_blind()
    replay_auditors()
    print("Prepared 22 blinded rows and replayed nine offline auditor cohorts.")
