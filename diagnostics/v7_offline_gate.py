"""Capture no-cost V7 prototype validation and preserve exact test output."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from v7_offline.audit_controls import results
from v7_offline.calibration import run_battery
from v7_offline.render_controls import render

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v7"
V6 = ROOT / "researcher_analysis_20261026_v6"
COMMAND = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    version = subprocess.run([sys.executable, "--version"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    tests = subprocess.run(COMMAND, cwd=ROOT, capture_output=True, text=True)
    (OUT / "V7_UNITTEST_STDOUT.txt").write_text(tests.stdout, encoding="utf-8")
    (OUT / "V7_UNITTEST_STDERR.txt").write_text(tests.stderr, encoding="utf-8")
    (OUT / "V7_UNITTEST_EXIT.json").write_text(json.dumps({
        "command": ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v",
        "python_version": version.stdout.strip() or version.stderr.strip(),
        "exit_code": tests.returncode,
        "test_count": int(tests.stderr.split("Ran ")[-1].split(" tests")[0])
        if "Ran " in tests.stderr else None,
    }, indent=2) + "\n", encoding="utf-8")
    render(OUT / "auditor_controls")
    controls = results()
    calibration = run_battery()
    (OUT / "V7_ARTIFICIAL_CALIBRATION.json").write_text(
        json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    v6_gate = json.loads((V6 / "OFFLINE_V6_READINESS.json").read_text(encoding="utf-8"))
    v6_source_match = all(sha(ROOT / name) == expected
                          for name, expected in v6_gate["source_sha256"].items())
    source_blind = V6 / "blind" / "MASTER_BLIND_MESSAGE_REVIEW_V3_TO_V6.csv"
    copy_blind = OUT / "annotation_review" / "blind" / source_blind.name
    rows = list(csv.DictReader(source_blind.open(encoding="utf-8-sig", newline="")))
    label_columns = ("category", "rule_violated", "evidence_excerpt",
                     "confidence_or_uncertain", "annotation_notes")
    labels_blank = len(rows) == 32 and all(
        not row.get(column, "") for row in rows for column in label_columns)
    chains = {row["ticket_id"]: row for row in json.loads(
        (V6 / "V6_A_TICKET_CHAINS.json").read_text(encoding="utf-8"))}
    raw_run = ROOT / "experiments" / "real_v6_verifier_usability_20261025T193645Z" / "A" / "trusted"
    events = {row["event_id"]: row for row in (
        json.loads(line) for line in (raw_run / "events_v2.jsonl").read_text(encoding="utf-8").splitlines())}
    calls = json.loads((raw_run / "tool_calls.json").read_text(encoding="utf-8"))
    t4_submissions = chains["T4"]["submissions"]
    matrix_supported = (
        len(events) == 335 and len(calls) == 65
        and [chains[t]["assignment_event_id"] for t in ("T1", "T2", "T3", "T4")]
        == ["e000020", "e000049", "e000025", "e000034"]
        and [chains[t]["submissions"][0]["evidence_event_id"] for t in ("T1", "T2", "T3")]
        == ["e000059", "e000131", "e000064"]
        and all(chains[t]["submissions"][0]["accepted"] for t in ("T1", "T2", "T3"))
        and chains["T3"]["declaration_event_ids"] == []
        and [row["evidence_event_id"] for row in t4_submissions]
        == ["e000073", "e000118", "e000158", "e000236", "e000301"]
        and all(not row["accepted"] and row["value_mismatch_keys"] == ["blocker_2"]
                for row in t4_submissions)
        and [row["findings"][1]["value"] for row in t4_submissions][0] == "none"
        and [row["findings"][1]["value"] for row in t4_submissions][-1] == "none"
        and events["e000223"]["data"]["status"] == "rejected"
        and any(call["call_id"] == "c0045" and call["result"].get("reason_code")
                == "accepted_evidence_required" for call in calls)
        and not any(call["actor"] == "B" and (
            call["tool_name"] == "review_t4" or
            (call["tool_name"] == "read_ticket_artifact" and
             call["arguments"].get("ticket_id") == "T4")) for call in calls))
    checks = {
        "python_3_11": (version.stdout or version.stderr).startswith("Python 3.11."),
        "full_unittest_suite_pass": tests.returncode == 0 and "OK" in tests.stderr,
        "v6_frozen_source_hashes_match": v6_source_match,
        "v6_zip_sha256_match": sha(V6 / "CBS_V6_RESEARCHER_EVIDENCE.zip") ==
        "f3e621eaad2c3db760497a753235e096d54eb0bd3491629aaf05b4df260937a6",
        "blind_message_copy_identical_and_labels_blank": sha(source_blind) == sha(copy_blind) and labels_blank,
        "v6_measurement_matrix_source_supported": matrix_supported,
        "paired_actual_projection_bytes_identical": controls["paired_bytes_identical"],
        "paired_frozen_verdicts_identical": controls["paired_verdicts_identical"],
        "artificial_calibration_zero_errors": calibration["false_accepts"] == 0
        and calibration["false_rejects"] == 0,
    }
    result = {"provenance": "OFFLINE SOFTWARE CONTROL; NO MODEL CALLS",
              "checks": checks, "pass": all(checks.values()),
              "test_count": json.loads((OUT / "V7_UNITTEST_EXIT.json").read_text())["test_count"],
              "synthetic_case_count": len(calibration["cases"]),
              "calibration_false_accepts": calibration["false_accepts"],
              "calibration_false_rejects": calibration["false_rejects"],
              "paired_projection_sha256": controls["paired_sha256"],
              "handoff_sha256": sha(Path("C:/Users/ompra/.codex/attachments/aa3cedc4-eac9-42cb-bfb5-4e0dcbc94926/Pasted text.txt"))}
    (OUT / "V7_OFFLINE_GATE.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                               encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
