"""Create a researcher-only ZIP from an explicit offline allowlist."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "researcher_analysis_20261025_v5"
RUN = ROOT / "experiments/real_v5_longer_horizon_20261025T164017Z"
ZIP = OUT / "CBS_V5_EVIDENCE_AND_REPORT_REVIEW.zip"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def add_file(payloads: dict[str, bytes], archive_path: str, source: Path) -> None:
    if archive_path in payloads:
        raise ValueError(f"Duplicate archive path: {archive_path}")
    payloads[archive_path] = source.read_bytes()


def source_snippets() -> bytes:
    ranges = {
        "protocol_v3.py": [(16, 19), (224, 239), (297, 316)],
        "world_v3.py": [(52, 77), (122, 166), (217, 266), (365, 380)],
        "world_v4.py": [(55, 77)],
        "agent_adapter_v3.py": [(31, 76)],
        "run_real_modal_v5.py": [(35, 35), (251, 312)],
        "audit_projection_v2.py": [(13, 69)],
        "audit_rules_v3.py": [(11, 77)],
        "run_mock_v3.py": [(16, 70)],
    }
    sections = ["# Bounded source excerpts with original line numbers\n\nThese are verification excerpts, not the full authoritative source.\n"]
    for file, spans in ranges.items():
        lines = (ROOT / file).read_text(encoding="utf-8").splitlines()
        for start, end in spans:
            sections.append(f"\n## {file}:{start}-{end}\n\n```python\n")
            sections.extend(f"{number:4d}: {lines[number-1]}\n" for number in range(start, min(end, len(lines)) + 1))
            sections.append("```\n")
    return "".join(sections).encode("utf-8")


def main() -> None:
    payloads: dict[str, bytes] = {}
    analysis = [
        "V5_CELL_A_FORENSIC_DIAGNOSIS.md", "V5_A_58_TURNS.csv", "V5_TICKET_CHAINS.json",
        "V5_COMMUNICATION_CAUSAL_CHAIN.csv", "V5_AUDITOR_REPLAY.json", "V5_OFFLINE_INTEGRITY.json",
        "AUDITOR_DECISIONS.csv", "AUDITOR_REPLAY_SUMMARY.json", "SCIENTIFIC_GO_NO_GO.md",
        "COLLECTIVE_BLIND_SPOT_REPORT_DRAFT_FOR_REVIEW.md", "SOURCE_REFERENCE_INDEX.md",
        "OFFLINE_UNITTEST_STDOUT_STDERR.txt", "OFFLINE_UNITTEST_EXIT.json",
        "blind/MASTER_BLIND_MESSAGE_REVIEW.csv", "blind/ANNOTATOR_README_AND_RUBRIC.md",
        "researcher_only/MASTER_ROW_LINKAGE.csv",
        "scripted_benign_v3_mock/auditor/verdicts.jsonl",
        "scripted_benign_v3_mock/auditor/pooled_metadata.jsonl",
        "scripted_benign_v3_mock/trusted/outcome.json",
    ]
    for relative in analysis:
        add_file(payloads, relative.replace("\\", "/"), OUT / relative)
    original = [
        "SOURCE_AND_EVIDENCE_SHA256.json", "V5_LIVE_DECISION.json", "VALIDATION.json",
        "A/VALIDATION.json", "A/manifest.json", "A/auditor/projections/pooled_metadata.jsonl",
        "A/auditor/verdicts.jsonl", "usage.json", "MODAL_STOP_VERIFICATION.json",
    ]
    for relative in original:
        add_file(payloads, f"saved_v5/{relative}", RUN / relative)
    add_file(payloads, "source/V5_HORIZON_DIFF.md", ROOT / "V5_HORIZON_DIFF.md")
    add_file(payloads, "source/OFFLINE_V5_READINESS.json", ROOT / "OFFLINE_V5_READINESS.json")
    add_file(payloads, "source/diagnostics_v5_behavioral_autopsy.py", ROOT / "diagnostics/v5_behavioral_autopsy.py")
    add_file(payloads, "source/diagnostics_prepare_v5_review.py", ROOT / "diagnostics/prepare_v5_review.py")
    payloads["source/BOUNDED_SOURCE_SNIPPETS.md"] = source_snippets()
    replay = RUN / "index.html"
    assert replay.is_file()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    inventory = {
        "package_role": "RESEARCHER_ONLY_NOT_FOR_BLIND_ANNOTATOR",
        "analysis_git_HEAD_before_new_commit": head,
        "v5_live_source_commit": "44d605844a29af34db12db63ec90e094d1683496",
        "v5_live_run": str(RUN.relative_to(ROOT)),
        "v5_replay": str(replay),
        "reproduction_commands": [
            r".\.venv\Scripts\python.exe diagnostics/v5_behavioral_autopsy.py",
            r".\.venv\Scripts\python.exe diagnostics/prepare_v5_review.py",
            r".\.venv\Scripts\python.exe -m unittest discover -s tests -v",
        ],
        "new_model_or_gpu_calls": 0,
        "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(payloads.items())},
    }
    payloads["PACKAGE_MANIFEST.json"] = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with ZipFile(ZIP, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(name, data)
    with ZipFile(ZIP) as archive:
        for name, meta in inventory["files"].items():
            assert sha(archive.read(name)) == meta["sha256"]
        assert set(archive.namelist()) == set(payloads)
    digest = sha(ZIP.read_bytes())
    (OUT / "CBS_V5_EVIDENCE_AND_REPORT_REVIEW.sha256").write_text(f"{digest}  {ZIP.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(ZIP), "sha256": digest, "file_count": len(payloads), "bytes": ZIP.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
