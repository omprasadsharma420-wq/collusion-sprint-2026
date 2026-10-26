"""Portable hash-verified full project archive; never include credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".env", ".pem", ".key", ".p12", ".pfx"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def include(path: Path) -> bool:
    if not path.is_file() or any(part in {"__pycache__", ".git", ".venv",
                                           ".pytest_cache", ".mypy_cache"}
                                     for part in path.parts):
        return False
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.lower().startswith(".env"):
        return False
    if path.name.lower() in {"modal.toml", "credentials.json", "token.json"}:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r-segment", type=Path, action="append", required=True)
    parser.add_argument("--p-run", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output archive already exists; never overwrite a frozen package")
    # Full project inventory preserves historical source, controls, raw runs,
    # diagnostics and analyses alongside V8. The three run arguments are checked
    # so a misplaced path cannot silently produce an incomplete archive.
    required = [*args.r_segment, args.p_run, args.analysis]
    for directory in required:
        if not directory.is_dir() or not directory.resolve().is_relative_to(ROOT):
            parser.error(f"Required evidence directory missing or outside project: {directory}")
    essential = [args.analysis / "CBS_V7_RAW_EVIDENCE_FOR_CHATGPT.zip",
                 args.analysis / "V8_R_RAW_AUDIT.json",
                 args.analysis / "V8_P_RAW_AUDIT.json",
                 args.analysis / "V8_FINAL_BILLING_AND_STOP.json",
                 args.analysis / "RESEARCH_EVIDENCE_LEDGER_V3_TO_V8.csv",
                 args.analysis / "README_REVIEW_FIRST.md"]
    if any(not path.is_file() for path in essential):
        parser.error("An essential review or raw-evidence file is missing")
    # The continuation manifest lists the first pair as carried history, while
    # its own folder contains only episodes 3–24. Count physical raw episodes.
    r_episodes = [key for segment in args.r_segment for key in json.loads((
        segment / "run_manifest.json").read_text(encoding="utf-8"))[
            "episodes_saved"] if (segment / key / "episode_manifest.json").is_file()]
    p_manifest = json.loads((args.p_run / "run_manifest.json").read_text(
        encoding="utf-8"))
    if len(r_episodes) != 24 or len(set(r_episodes)) != 24 or len(p_manifest[
            "episodes_saved"]) != 12 or p_manifest[
            "status"] != "TECHNICAL_STOP":
        parser.error("Run inventory differs from independently audited V8 counts")
    paths = sorted(set(path.resolve() for path in ROOT.rglob("*") if include(path)
                       and path.resolve() != args.output.resolve()))
    for path in paths:
        if not path.is_relative_to(ROOT):
            parser.error(f"Archive path escaped project: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"archive_type": "CBS_V8_RESEARCHER_FULL_EVIDENCE",
                "contains_privileged_truth_and_private_model_inputs": True,
                "blind_reviewers_must_receive_only_blind_human_review_subfolder": True,
                "inventory_scope": "Every non-credential file in the local project workspace, "
                                   "including historical runs and source snapshots; excludes "
                                   "virtual environments, caches and credential-like files",
                "files": {}}
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in paths:
            arc = path.relative_to(ROOT).as_posix()
            raw = path.read_bytes()
            archive.writestr(arc, raw)
            manifest["files"][arc] = {"sha256": sha(raw), "bytes": len(raw)}
        archive.writestr("V8_ARCHIVE_SHA256_MANIFEST.json", json.dumps(
            manifest, indent=2, sort_keys=True) + "\n")
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        for name, info in manifest["files"].items():
            raw = archive.read(name)
            if len(raw) != info["bytes"] or sha(raw) != info["sha256"]:
                raise RuntimeError(f"ZIP file digest mismatch: {name}")
    print(args.output.resolve())
    print("sha256=" + sha(args.output.read_bytes()))
    print("files=" + str(len(paths)))


if __name__ == "__main__":
    main()
