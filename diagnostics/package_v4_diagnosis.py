"""Package a sanitized, independently inspectable v4 Cell A diagnosis."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/real_v4_schema_visible_20261025T160532Z"
RESEARCHER = RUN / "researcher"
DETAIL = RESEARCHER / "v4_a_diagnosis"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    snippets = [
        ("protocol_v3.py", 325, 336),
        ("world_v3.py", 52, 77),
        ("world_v3.py", 122, 165),
        ("world_v3.py", 217, 269),
        ("world_v3.py", 317, 377),
        ("world_v4.py", 30, 132),
        ("agent_adapter_v3.py", 31, 83),
        ("run_real_modal_v4.py", 66, 175),
        ("run_real_modal_v4.py", 255, 327),
        ("audit_projection_v2.py", 35, 90),
        ("audit_rules_v3.py", 11, 75),
    ]
    blocks = ["# Numbered source excerpts — researcher forensic review\n",
              "Pinned runtime source commit: `a9e863f43d0367cda1122f48a29795baca0e748c`. ",
              "These are excerpts, not executable source. The private memo literal and ",
              "full raw agent inputs are excluded.\n"]
    for name, start, stop in snippets:
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        blocks += [f"\n## `{name}:{start}`–`{stop}`\n", "```python"]
        blocks += [f"{line:04d}: {lines[line - 1]}" for line in range(start, min(stop, len(lines)) + 1)]
        blocks += ["```\n"]
    source_file = DETAIL / "SOURCE_SNIPPETS.md"
    source_file.write_text("\n".join(blocks), encoding="utf-8")
    selected = [
        RESEARCHER / "V4_CELL_A_CAUSAL_DIAGNOSIS.md",
        RESEARCHER / "V4_DIAGNOSIS_OFFLINE_TESTS.txt",
        DETAIL / "V4_A_TURNS.csv", DETAIL / "TICKET_STATE_CHAINS.json",
        DETAIL / "DELIVERY_READ_INPUT_AUDIT.csv",
        DETAIL / "AUDITOR_REPLAY_EXCERPTS.json",
        DETAIL / "SOURCE_FINGERPRINTS.json", DETAIL / "INTEGRITY_GATE.json",
        source_file,
        RUN / "A/EXPERIMENT_SUMMARY.md", RUN / "A/VALIDATION.json",
        RUN / "A/trusted/outcome.json", RUN / "A/auditor/verdicts.jsonl",
        RUN / "V4_LIVE_DECISION.json", RUN / "comparison.csv",
        ROOT / "V4_MODEL_VISIBLE_DIFF.md", ROOT / "PROMPT_HASHES_V4.json",
        ROOT / "OFFLINE_V4_READINESS.json",
    ]
    manifest = {
        "label": "RESEARCHER-ONLY V4 CAUSAL DIAGNOSIS; NOT A BLIND ANNOTATOR PACKET",
        "v4_source_commit": "a9e863f43d0367cda1122f48a29795baca0e748c",
        "read_only_analysis": True,
        "raw_provider_requests_or_responses_in_zip": False,
        "message_bodies_in_zip": False,
        "selected_file_sha256": {str(path.relative_to(ROOT)).replace('\\', '/'): sha(path)
                                 for path in selected},
    }
    manifest_path = DETAIL / "REPRO_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selected.append(manifest_path)
    archive_path = RESEARCHER / "CBS_V4_A_DIAGNOSIS_REVIEW.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in selected:
            archive.write(path, str(path.relative_to(ROOT)).replace('\\', '/'))
    digest = sha(archive_path)
    (RESEARCHER / "CBS_V4_A_DIAGNOSIS_REVIEW_SHA256.txt").write_text(
        f"{digest}  CBS_V4_A_DIAGNOSIS_REVIEW.zip\n", encoding="utf-8")
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert not any("model_inputs/" in name or "trusted_provider_calls/" in name
                       for name in archive.namelist())
    print(json.dumps({"zip": str(archive_path), "sha256": digest,
                      "files": len(selected)}, indent=2))


if __name__ == "__main__":
    main()
