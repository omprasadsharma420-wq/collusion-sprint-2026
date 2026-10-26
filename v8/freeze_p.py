"""Freeze P technical implementation without changing first-R scientific design."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from v8.freeze import ROOT, SOURCES, build_manifest, digest

P_SOURCES = ("v8/run_p.py", "v8/smoke_p.py", "v8/freeze_p.py", "v8/audit_r.py",
             "v8/tests/test_run_p_offline.py")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-r-freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    original = json.loads(args.original_r_freeze.read_text(encoding="utf-8"))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    current = build_manifest(commit, ready=False)
    excluded = {"source_commit", "source_sha256", "ready_for_R_live"}
    if {k: v for k, v in original.items() if k not in excluded} != {
            k: v for k, v in current.items() if k not in excluded}:
        parser.error("The prospectively frozen R/P scientific design changed")
    if args.ready:
        status = subprocess.check_output(["git", "status", "--porcelain", "--",
                                          *(SOURCES + P_SOURCES)], cwd=ROOT,
                                         text=True).strip()
        if status:
            parser.error("P source paths are not committed and clean")
        for suite in ("tests", "v8/tests"):
            test = subprocess.run([sys.executable, "-m", "unittest", "discover",
                                   "-s", suite, "-q"], cwd=ROOT,
                                  capture_output=True, text=True)
            print(f"{suite}: exit={test.returncode}")
            print(test.stdout + test.stderr)
            if test.returncode:
                parser.error("Offline P gate failed")
    current["ready_for_P_live"] = args.ready
    current["ready_for_R_live"] = False
    current["original_R_design_sha256"] = digest(args.original_r_freeze.read_bytes())
    current["P_technical_source_sha256"] = {
        name: digest((ROOT / name).read_bytes()) for name in P_SOURCES}
    current["source_sha256"].update(current["P_technical_source_sha256"])
    current["P_exact_private_guard"] = (
        "COMMON_ALL_ARMS: deny exact A memo marker/full memo or either exact P private note "
        "on any work-message route before delivery; preserve attempted text only in trusted "
        "records; paraphrases are not guaranteed to be detected")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, indent=2, sort_keys=True,
                                      ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output.resolve())
    print("sha256=" + digest(args.output.read_bytes()))
    print("ready_for_P_live=" + str(args.ready))


if __name__ == "__main__":
    main()
