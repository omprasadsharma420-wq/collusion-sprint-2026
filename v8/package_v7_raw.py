"""Create and verify one portable V7 raw evidence archive; no cloud upload."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/real_v7_balanced_20261025T232433Z"
OUT = ROOT / "researcher_analysis_20261026_v8"
TARGET = OUT / "CBS_V7_RAW_EVIDENCE_FOR_CHATGPT.zip"
AUDIT_FILES = (
    "V7_RAW_INDEPENDENT_AUDIT.md",
    "V7_PER_EPISODE_SUMMARY.csv",
    "V7_EXPOSURE_OPPORTUNITY_AUDIT.csv",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    mapping: dict[str, Path] = {}
    for path in RUN.rglob("*"):
        if path.is_file():
            arc = "V7_RUN/" + path.relative_to(RUN).as_posix()
            mapping[arc] = path
    for name in AUDIT_FILES:
        mapping["V7_INDEPENDENT_AUDIT/" + name] = OUT / name
    assert all(path.is_file() for path in mapping.values())
    assert not any(path.name.startswith(".env") or path.suffix.lower() in {".pem", ".key"}
                   for path in mapping.values())
    required = [
        "V7_RUN/V7_FROZEN_MANIFEST.json", "V7_RUN/V7_VALIDATION.json",
        "V7_RUN/V7_MESSAGE_CAUSAL_PATHS.csv", "V7_RUN/V7_RESPONSE_PROVENANCE.csv",
        "V7_RUN/V7_EPISODE_CONSTANCY.json", "V7_RUN/SMOKE_NOT_DATA.json",
        "V7_RUN/SOURCE_SNAPSHOT_SHA256.json",
    ]
    for index, cell in enumerate("CADBBDAC", 1):
        key = f"{index:02d}_{cell}"
        required += [f"V7_RUN/{key}/trusted/events_v2.jsonl",
                     f"V7_RUN/{key}/trusted/tool_calls.json",
                     f"V7_RUN/{key}/auditor/pooled_metadata.jsonl",
                     f"V7_RUN/{key}/auditor/verdicts.jsonl",
                     f"V7_RUN/{key}/manifest.json"]
    assert all(item in mapping for item in required)
    hashes = {name: sha(path.read_bytes()) for name, path in sorted(mapping.items())}
    manifest = {"classification": "RESEARCHER_ONLY_RAW_EVIDENCE",
                "source_commit": "5ccbce13bcfedb4bcabf8df68467a3db8a9c7164",
                "run_root": RUN.name, "included_files_sha256": hashes,
                "scientific_note": "No independent ChatGPT or human review implied by creation of this archive."}
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with zipfile.ZipFile(TARGET, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for name, path in sorted(mapping.items()):
            archive.write(path, arcname=name)
        archive.writestr("V7_RAW_ARCHIVE_MANIFEST.json", manifest_raw)
    with zipfile.ZipFile(TARGET) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(mapping) | {"V7_RAW_ARCHIVE_MANIFEST.json"}
        for name, expected in hashes.items():
            assert sha(archive.read(name)) == expected
    (TARGET.with_suffix(".sha256")).write_text(
        f"{sha(TARGET.read_bytes())}  {TARGET.name}\n", encoding="utf-8")
    print(json.dumps({"path": str(TARGET), "files": len(mapping) + 1,
                      "zip_sha256": sha(TARGET.read_bytes()), "integrity": "PASS"}, indent=2))


if __name__ == "__main__":
    main()
