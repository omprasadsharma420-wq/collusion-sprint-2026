"""Independent offline consistency audit of saved V6 evidence and review ZIP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    run = args.run_root.resolve()
    manifest = load(run / "run_manifest.json")
    readiness = load(OUT / "OFFLINE_V6_READINESS.json")
    summary = load(OUT / "V6_REAL_RESULTS.json")
    checks = {}
    checks["source_commit_and_offline_gate_match"] = (
        readiness["offline_gate_pass"] is True
        and manifest["source_commit"] == readiness["source_commit"] == summary["source_commit"])
    checks["source_hashes_still_match"] = all(
        sha((ROOT / path).read_bytes()) == digest for path, digest in readiness["source_sha256"].items())
    suite = load(OUT / "OFFLINE_V6_UNITTEST_EXIT.json")
    stderr = (OUT / "OFFLINE_V6_UNITTEST_STDERR.txt").read_text(encoding="utf-8")
    checks["original_and_new_tests_pass"] = (
        suite["exit_code"] == 0 and re.search(r"Ran 79 tests.*?\n\s*OK\s*$", stderr, re.S) is not None)
    patch = OUT / "V6_SOURCE_DIFF.patch"
    patch_check = subprocess.run(["git", "apply", "--cached", "--reverse", "--check", str(patch)],
                                 cwd=ROOT, capture_output=True, text=True)
    checks["source_diff_reverse_applies_to_index"] = patch_check.returncode == 0
    validation = load(run / "VALIDATION.json")
    cell_validation = load(run / "A/VALIDATION.json")
    decision = load(run / "V6_LIVE_DECISION.json")
    checks["saved_provider_trace_and_pilot_gate"] = (
        validation["model_calls"] == cell_validation["validated_provider_calls"] == 67
        and cell_validation["validation_ok"] is True
        and cell_validation["events"] == 335 and cell_validation["task_score"] == 2
        and decision["pilot_pass"] is False
        and all(not decision[f"{cell.lower()}_ran"] for cell in "BCD"))
    receipts = [load(path) for path in sorted((run / "trusted_provider_calls").glob("*/receipt.json"))]
    checks["unique_pinned_provider_responses"] = (
        len(receipts) == len({r["response_id"] for r in receipts}) == 67
        and all(r["status"] == 200 and r["model"] == manifest["model"]
                and r["revision"] == manifest["revision"] for r in receipts))
    provenance = load(OUT / "V6_RAW_PROVENANCE_INDEX.json")
    mismatches = []
    for entry in provenance["raw_files_not_in_zip"]:
        path = ROOT / entry["path_from_repo_root"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha(path.read_bytes()) != entry["sha256"]:
            mismatches.append(entry["path_from_repo_root"])
    checks["all_raw_provenance_hashes_match"] = len(mismatches) == 0 and len(provenance["raw_files_not_in_zip"]) >= 400
    blind_path = OUT / "blind/MASTER_BLIND_MESSAGE_REVIEW_V3_TO_V6.csv"
    with blind_path.open(newline="", encoding="utf-8") as stream:
        blind = list(csv.DictReader(stream))
    with (OUT / "researcher_only/MASTER_ROW_LINKAGE_V3_TO_V6.csv").open(newline="", encoding="utf-8") as stream:
        linkage = list(csv.DictReader(stream))
    checks["blind_packet_unlabeled_and_linkage_separate"] = (
        len(blind) == len(linkage) == 32
        and {row["row_id"] for row in blind} == {row["row_id"] for row in linkage}
        and all(not any(row[key] for key in ("category", "rule_violated", "evidence_excerpt",
                                               "confidence_or_uncertain", "annotation_notes")) for row in blind)
        and "M1-R1-7C42" not in blind_path.read_text(encoding="utf-8")
        and "source_event_id" not in blind_path.read_text(encoding="utf-8"))
    obs = (OUT / "V6_OBSERVATION_PROVENANCE.csv").read_text(encoding="utf-8").splitlines()
    checks["one_provider_linked_observation"] = len(obs) == 2 and "e000288" in obs[1] and "e000287" in obs[1]
    auditor = (OUT / "V6_AUDITOR_REPLAY.csv").read_text(encoding="utf-8").splitlines()
    checks["three_frozen_no_alert_candidates"] = len(auditor) == 4 and all(",no_alert," in row for row in auditor[1:])
    cost = load(run / "MODAL_COST_AND_STOP_VERIFICATION.json")
    checks["modal_stopped_zero_tasks_cost_distinguished"] = (
        cost["app_stop_verification"]["state"] == "stopped"
        and cost["app_stop_verification"]["tasks"] == "0"
        and cost["per_app_billed_usd"] == "NOT_REPORTED_BY_MODAL"
        and cost["workspace_october_billed_usd_at_read"] == "0E-8")
    replay = run / "index.html"
    local_refs = re.findall(r'(?:href|src)="([^"]+)"', replay.read_text(encoding="utf-8"))
    checks["researcher_replay_local_links_resolve"] = replay.is_file() and all(
        (replay.parent / ref.split("#")[0].split("?")[0]).exists()
        for ref in local_refs if not ref.startswith(("http:", "https:", "#", "data:")))
    zip_path = OUT / "CBS_V6_RESEARCHER_EVIDENCE.zip"
    with ZipFile(zip_path) as archive:
        package = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        checks["zip_manifest_and_no_private_raw"] = (
            all(sha(archive.read(name)) == item["sha256"] for name, item in package["files"].items())
            and set(archive.namelist()) == set(package["files"]) | {"PACKAGE_MANIFEST.json"}
            and not any("trusted_provider_calls" in name or "model_inputs/" in name
                        or "model_outputs/" in name for name in archive.namelist()))
        checks["zip_contains_current_key_reports"] = all(
            archive.read(name) == (OUT / name).read_bytes()
            for name in ("V6_SOURCE_DIFF.patch", "V6_EVIDENCE_AND_SCIENTIFIC_DECISION.md",
                         "COLLECTIVE_BLIND_SPOT_REPORT_WORKING_DRAFT_V6.md",
                         "blind/MASTER_BLIND_MESSAGE_REVIEW_V3_TO_V6.csv",
                         "V6_RAW_PROVENANCE_INDEX.json"))
    saved_sha = (OUT / "CBS_V6_RESEARCHER_EVIDENCE.sha256").read_text(encoding="utf-8").split()[0]
    checks["zip_external_sha256_matches"] = saved_sha == sha(zip_path.read_bytes())
    result = {"verification_pass": all(checks.values()), "checks": checks,
              "raw_hash_mismatches": mismatches, "raw_index_entries": len(provenance["raw_files_not_in_zip"]),
              "run_source_commit": manifest["source_commit"], "zip_sha256": saved_sha}
    (OUT / "V6_FINAL_OFFLINE_VERIFICATION.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["verification_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
