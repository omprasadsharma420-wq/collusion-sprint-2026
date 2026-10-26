"""Assemble one researcher-only V6 ZIP without private raw provider/agent traces."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261026_v6"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def add(files: dict[str, bytes], archive_name: str, path: Path) -> None:
    if archive_name in files:
        raise ValueError(f"Duplicate archive entry: {archive_name}")
    files[archive_name] = path.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root.resolve()
    if not run.is_relative_to(ROOT / "experiments") or not run.name.startswith("real_v6_verifier_usability_"):
        raise ValueError("Expected V6 saved run under experiments")
    live = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    raw_roots = [run / "trusted_provider_calls"]
    raw_roots += [run / cell / "trusted" for cell in "ABCD" if (run / cell / "trusted").exists()]
    raw_roots += [run / cell / "researcher" for cell in "ABCD" if (run / cell / "researcher").exists()]
    raw_index = []
    for raw_root in raw_roots:
        for path in sorted(p for p in raw_root.rglob("*") if p.is_file()):
            raw_index.append({"path_from_repo_root": str(path.relative_to(ROOT)).replace("\\", "/"),
                              "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size})
    (OUT / "V6_RAW_PROVENANCE_INDEX.json").write_text(json.dumps({
        "run_source_commit": live["source_commit"],
        "raw_files_not_in_zip": raw_index,
        "note": "Private raw model/provider and trusted oracle records remain only in the saved local run. The review ZIP includes hashes, not their contents.",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analyses = [
        "V6_CHANGE_SPEC.md", "V6_MEASUREMENT_RATIONALE.md", "V6_SOURCE_DIFF.patch",
        "OFFLINE_V6_READINESS.md", "OFFLINE_V6_READINESS.json",
        "OFFLINE_V6_UNITTEST_STDOUT.txt", "OFFLINE_V6_UNITTEST_STDERR.txt",
        "OFFLINE_V6_UNITTEST_EXIT.json", "V6_REAL_RESULTS.json",
        "V6_EVIDENCE_AND_SCIENTIFIC_DECISION.md",
        "COLLECTIVE_BLIND_SPOT_REPORT_WORKING_DRAFT_V6.md",
        "PROPOSED_POSITIVE_EVIDENCE_STRESS_TEST_FOR_APPROVAL.md",
        "V6_A_67_TURNS.csv", "V6_A_TICKET_CHAINS.json",
        "V6_A_MESSAGE_CAUSAL_PATHS.csv", "V6_OBSERVATION_PROVENANCE.csv",
        "V6_AUDITOR_REPLAY.csv", "V6_RAW_PROVENANCE_INDEX.json",
        "blind/MASTER_BLIND_MESSAGE_REVIEW_V3_TO_V6.csv",
        "blind/ANNOTATOR_README_AND_RUBRIC.md",
        "researcher_only/MASTER_ROW_LINKAGE_V3_TO_V6.csv",
        "researcher_only/BLIND_PACKET_COUNTS.json",
        "researcher_only/FAILED_SUBMIT_WORK_V3_V4_V5.csv",
    ]
    files: dict[str, bytes] = {}
    for relative in analyses:
        add(files, relative.replace("\\", "/"), OUT / relative)
    saved = [
        "V6_LIVE_DECISION.json", "VALIDATION.json", "run_manifest.json",
        "comparison.csv", "EXPERIMENT_SUMMARY.md", "usage.json",
        "MODAL_COST_AND_STOP_VERIFICATION.json", "MODAL_STOP_VERIFICATION.json",
        "A/VALIDATION.json", "A/manifest.json",
        "A/auditor/pooled_metadata.jsonl", "A/auditor/verdicts.jsonl",
    ]
    for relative in saved:
        add(files, f"saved_run/{relative}", run / relative)
    replay = run / "index.html"
    assert replay.is_file() and (run / "A/researcher/replay.html").is_file()
    command = f"Start-Process -FilePath '{replay}'\n"
    files["REPLAY_COMMAND.txt"] = command.encode("utf-8")
    manifest = {
        "package_role": "RESEARCHER_ONLY_DO_NOT_SEND_TO_BLIND_ANNOTATOR",
        "run_source_commit": live["source_commit"],
        "saved_run_relative_path": str(run.relative_to(ROOT)).replace("\\", "/"),
        "model_calls_after_v6_run": 0,
        "private_raw_traces_in_zip": False,
        "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(files.items())},
    }
    files["PACKAGE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    zip_path = OUT / "CBS_V6_RESEARCHER_EVIDENCE.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == set(files)
        for name, metadata in manifest["files"].items():
            assert sha(archive.read(name)) == metadata["sha256"]
    digest = sha(zip_path.read_bytes())
    (OUT / "CBS_V6_RESEARCHER_EVIDENCE.sha256").write_text(
        f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(zip_path), "sha256": digest,
                      "entries": len(files), "raw_index_entries": len(raw_index),
                      "bytes": zip_path.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
