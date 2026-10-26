"""Independent read-only consistency check of the saved V7 freeze manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modal_transport_v7 import BLOCK_SEEDS, MAX_GENERATION_TOKENS, MODEL_NAME, MODEL_REVISION, TEMPERATURE
from protocol_v3 import AGENTS, ARTIFACTS, CellConfig
from protocol_v7 import TOOL_SCHEMAS, first_user_text, system_text, tool_schema_sha256
from run_real_modal_v7 import SCHEDULE
from truth_v7 import EXPECTED


def main() -> None:
    out = ROOT / "researcher_analysis_20261026_v7_live"
    saved = json.loads((out / "V7_FROZEN_MANIFEST.json").read_text(encoding="utf-8"))
    readiness = json.loads((out / "V7_OFFLINE_READINESS.json").read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()
    agent = saved["agent_visible_initial"]
    checks = {
        "commit_matches_source_and_readiness": head == saved["source_commit_at_generation"] == readiness["source_commit"],
        "all_source_bytes_match": saved["source_files_sha256"] == readiness["source_sha256"] and all(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
            for path, digest in saved["source_files_sha256"].items()),
        "all_eight_system_bytes_match": all(
            agent["system"][reminder][actor] == system_text(
                actor, CellConfig.for_cell("B" if reminder == "ON" else "A"))
            for reminder in ("ON", "OFF") for actor in AGENTS),
        "all_four_first_user_bytes_match": all(
            agent["first_user"][actor] == first_user_text(actor) for actor in AGENTS),
        "ordered_tools_match": agent["ordered_tools"] == TOOL_SCHEMAS and
            agent["tool_schema_sha256"] == tool_schema_sha256(),
        "artifacts_match": saved["source_artifacts_on_eligible_read_only"] == ARTIFACTS,
        "private_truth_matches_server": saved["researcher_only_hidden_key"] == {
            key: dict(value) for key, value in EXPECTED.items()},
        "treatment_map_matches": all(saved["treatment_map"][cell] == {
            "gate_known_direct": CellConfig.for_cell(cell).gate_known_direct,
            "reporting_reminder": CellConfig.for_cell(cell).reporting_reminder}
            for cell in "ABCD"),
        "schedule_and_seed_match": saved["schedule"] == [
            {"episode_key": f"{index:02d}_{cell}", "block": block,
             "cell": cell, "requested_seed": BLOCK_SEEDS[block]}
            for index, (block, cell) in enumerate(SCHEDULE, 1)],
        "model_config_matches": saved["model"]["name"] == MODEL_NAME and
            saved["model"]["revision"] == MODEL_REVISION and
            saved["model"]["temperature"] == TEMPERATURE and
            saved["model"]["max_generation_tokens"] == MAX_GENERATION_TOKENS,
    }
    result = {"checks": checks, "pass": all(checks.values()), "source_commit": head,
              "provenance": "READ_ONLY OFFLINE INDEPENDENT VERIFICATION"}
    (out / "V7_MANIFEST_INDEPENDENT_VERIFY.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
