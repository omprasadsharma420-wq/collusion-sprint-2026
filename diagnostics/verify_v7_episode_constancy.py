"""Read-only cross-episode check of the frozen V7 treatment and initial input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modal_transport_v7 import BLOCK_SEEDS, MODEL_NAME, MODEL_REVISION, TEMPERATURE, VLLM_VERSION
from protocol_v3 import AGENTS, MEMO_MARKER, CellConfig
from protocol_v7 import TOOL_SCHEMAS, first_user_text, prompt_sha256, system_text, tool_schema_sha256
from run_real_modal_v7 import SCHEDULE
from trace_v2 import TraceV2


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_root.resolve()
    if not run.is_relative_to(ROOT / "experiments") or not run.name.startswith("real_v7_balanced_"):
        parser.error("Expected saved V7 real run root")
    freeze = load(run / "V7_FROZEN_MANIFEST.json")
    rows = []
    for index, (block, cell) in enumerate(SCHEDULE, 1):
        key = f"{index:02d}_{cell}"
        episode = run / key
        manifest = load(episode / "manifest.json")
        events = TraceV2.read_jsonl(episode / "trusted/events_v2.jsonl").events
        first = {actor: next(e for e in events if e.kind == "model_input_captured" and e.actor == actor)
                 for actor in AGENTS}
        first_requests = {actor: load(episode / "trusted" / event.data["input_ref"])
                          for actor, event in first.items()}
        exact = all(first_requests[actor] == {"messages": [
            {"role": "system", "content": system_text(actor, CellConfig.for_cell(cell))},
            {"role": "user", "content": first_user_text(actor)}],
            "tools": TOOL_SCHEMAS} for actor in AGENTS)
        source_ok = manifest["source_commit"] == freeze["source_commit_at_generation"]
        tool_ok = manifest["tool_schema_sha256"] == tool_schema_sha256()
        prompt_ok = manifest["prompt_sha256"] == {
            actor: prompt_sha256(actor, CellConfig.for_cell(cell)) for actor in AGENTS}
        memo_ok = (MEMO_MARKER in json.dumps(first_requests["A"]) and
                   all(MEMO_MARKER not in json.dumps(first_requests[actor]) for actor in "BCD"))
        treatment_ok = freeze["treatment_map"][cell] == {
            "gate_known_direct": CellConfig.for_cell(cell).gate_known_direct,
            "reporting_reminder": CellConfig.for_cell(cell).reporting_reminder}
        model_ok = (manifest["model"] == MODEL_NAME and manifest["revision"] == MODEL_REVISION and
                    manifest["vllm_version"] == VLLM_VERSION and manifest["temperature"] == TEMPERATURE and
                    manifest["seed"] == BLOCK_SEEDS[block])
        row = {"episode_key": key, "cell": cell, "block": block,
               "exact_initial_inputs": exact, "memo_initially_only_a": memo_ok,
               "source_commit_fixed": source_ok, "tool_schema_fixed": tool_ok,
               "prompt_hashes_correct": prompt_ok, "treatment_map_correct": treatment_ok,
               "model_and_block_seed_correct": model_ok}
        row["pass"] = all(v for k, v in row.items() if k not in {"episode_key", "cell", "block"})
        rows.append(row)
    result = {"pass": all(row["pass"] for row in rows), "episodes": rows,
              "all_eight_present": len(rows) == 8,
              "provenance": "READ_ONLY CROSS-EPISODE VALIDATION"}
    (run / "V7_EPISODE_CONSTANCY.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "episodes": len(rows)}, indent=2))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
