"""Fail-closed, no-cost V7 implementation gate before the isolated real smoke."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from modal_transport_v7 import (BLOCK_SEEDS, MAX_GENERATION_TOKENS, MODEL_NAME,
                                MODEL_REVISION, TEMPERATURE, VLLM_VERSION,
                                completion_request)
from protocol_v3 import AGENTS, ARTIFACTS, MEMO_MARKER, CellConfig
from protocol_v7 import TOOL_SCHEMAS, first_user_text, prompt_sha256, system_text
from run_real_modal_v7 import (MAX_GPU_WALL_SECONDS, MAX_RESPONSES_PER_AGENT,
                               MAX_SMOKE_CALLS, MAX_STUDY_CALLS, MAX_TOTAL_CALLS, SCHEDULE)
from v7_offline.audit_controls import results as paired_results
from v7_offline.proposal import candidate_first_user_text, candidate_system_text, candidate_tool_schemas
from verifier_v7 import REQUIRED_FIELDS, validate
from world_v3 import _validate_value
from world_v7 import WorldV7

OUT = ROOT / "researcher_analysis_20261026_v7_live"
SOURCE_FILES = (
    "protocol_v7.py", "truth_v7.py", "verifier_v7.py", "world_v7.py",
    "agent_adapter_v7.py", "modal_transport_v7.py", "run_real_modal_v7.py",
    "run_mock_v7.py", "diagnostics/extract_v7_approved_interface.py",
    "diagnostics/v7_live_gate.py", "diagnostics/build_v7_freeze.py",
    "tests/test_v7_approved_world.py",
    "tests/test_v7_transport_offline.py", "tests/test_v7_runner_offline.py",
    "v7_approved_interface/prompts.json", "v7_approved_interface/tools.json",
    "v7_approved_interface/source_provenance.json",
)
SCRIPTED = ROOT / "experiments/v7_approved_offline_fixture/valid_hold/SOFTWARE_CONTROL_SUMMARY.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    source_commit = git("rev-parse", "HEAD")
    prior = json.loads((ROOT / "researcher_analysis_20261026_v6/OFFLINE_V6_READINESS.json")
                       .read_text(encoding="utf-8"))["source_sha256"]
    prompts = json.loads((ROOT / "v7_approved_interface/prompts.json").read_text(encoding="utf-8"))
    provenance = json.loads((ROOT / "v7_approved_interface/source_provenance.json")
                            .read_text(encoding="utf-8"))
    candidate = candidate_tool_schemas()
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    checks: dict[str, bool] = {}
    checks["source_committed_and_clean"] = (all((ROOT / name).is_file() for name in SOURCE_FILES)
        and not git("status", "--porcelain", "--", *SOURCE_FILES))
    checks["v3_to_v6_frozen_files_unchanged"] = all(
        sha(ROOT / name) == expected for name, expected in prior.items())
    checks["exact_eight_system_and_four_user_prompts"] = all(
        system_text(actor, CellConfig.for_cell(cell)) ==
        candidate_system_text(actor, CellConfig.for_cell(cell).reporting_reminder)
        and first_user_text(actor) == candidate_first_user_text(actor)
        and len(prompt_sha256(actor, CellConfig.for_cell(cell))) == 64
        for cell in "ABCD" for actor in AGENTS) and all(
            set(prompts["system"][reminder]) == set(AGENTS) for reminder in ("ON", "OFF"))
    checks["prompt_treatment_is_only_last_reminder_sentence"] = all(
        system_text(actor, CellConfig.for_cell("A")).splitlines()[:-1] ==
        system_text(actor, CellConfig.for_cell("B")).splitlines()[:-1]
        for actor in AGENTS)
    checks["private_memo_initially_only_a"] = (
        MEMO_MARKER in first_user_text("A") and
        all(MEMO_MARKER not in first_user_text(actor) for actor in "BCD"))
    checks["ordered_12_tools_flat_replacement_only"] = (
        len(names) == 12 and names == [t["function"]["name"] for t in candidate]
        and names[9] == "submit_work"
        and all(new == old for new, old in zip(TOOL_SCHEMAS, candidate)
                if new["function"]["name"] != "submit_work")
        and TOOL_SCHEMAS[9]["function"]["parameters"].get("type") == "object"
        and "oneOf" not in json.dumps(TOOL_SCHEMAS[9]))
    checks["fixed_world_and_server_key_only"] = (
        set(ARTIFACTS) == set(REQUIRED_FIELDS) == {"T1", "T2", "T3", "T4"}
        and not any("EXPECTED" in text for text in
                    list(prompts["first_user"].values()) +
                    [x for d in prompts["system"].values() for x in d.values()]))
    schema = TOOL_SCHEMAS[9]["function"]["parameters"]
    from truth_v7 import EXPECTED
    try:
        for ticket, findings in EXPECTED.items():
            _validate_value(schema, {"ticket_id": ticket, "findings": dict(findings)})
            assert validate({"ticket_id": ticket, "findings": dict(findings)},
                            public_tools=TOOL_SCHEMAS).accepted
        json_schema_ok = True
    except (ValueError, AssertionError, TypeError):
        json_schema_ok = False
    checks["pure_python_flat_schema_and_server_requirements"] = json_schema_ok
    request = completion_request(json.dumps({"messages": [
        {"role": "system", "content": system_text("A", CellConfig.for_cell("A"))},
        {"role": "user", "content": first_user_text("A")}], "tools": TOOL_SCHEMAS}).encode(),
        seed=BLOCK_SEEDS[1])
    wire = json.loads(request)
    checks["openai_wire_static_12_schema_serialization"] = (
        wire["tools"] == TOOL_SCHEMAS and wire["seed"] == BLOCK_SEEDS[1]
        and wire["temperature"] == TEMPERATURE and wire["tool_choice"] == "auto")
    checks["scripted_reachable_hold_four_and_b_review"] = SCRIPTED.is_file() and (
        lambda fixture: fixture["outcome"]["task_score"] == 4
        and fixture["outcome"]["t4_review_correctness"] == "CORRECT_ACCEPT_HOLD"
        and fixture["outcome"]["invalid_release_approval"] is None
        and "SCRIPTED SOFTWARE CONTROL" in fixture["provenance"])(
            json.loads(SCRIPTED.read_text(encoding="utf-8")))
    pair = paired_results()
    checks["frozen_monitor_paired_control_unchanged"] = (
        pair["paired_bytes_identical"] and pair["paired_verdicts_identical"]
        and pair["cases"][0]["verdicts"] == pair["cases"][1]["verdicts"]
        and [v["rule_id"] for v in pair["cases"][0]["verdicts"]] == ["R1"])
    checks["balanced_schedule_and_operational_caps"] = (
        SCHEDULE == ((1, "C"), (1, "A"), (1, "D"), (1, "B"),
                     (2, "B"), (2, "D"), (2, "A"), (2, "C"))
        and MAX_RESPONSES_PER_AGENT == 24 and MAX_STUDY_CALLS == 768
        and MAX_SMOKE_CALLS == 3 and MAX_TOTAL_CALLS == 771
        and MAX_GPU_WALL_SECONDS == 10800 and MAX_GENERATION_TOKENS == 768
        and MODEL_NAME == "Qwen/Qwen3-8B-FP8"
        and MODEL_REVISION == "220b46e3b2180893580a4454f21f22d3ebb187d3"
        and VLLM_VERSION == "0.10.2")
    version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, check=True)
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                           cwd=ROOT, capture_output=True, text=True)
    (OUT / "V7_FULL_UNITTEST_STDOUT.txt").write_text(tests.stdout, encoding="utf-8")
    (OUT / "V7_FULL_UNITTEST_STDERR.txt").write_text(tests.stderr, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests.*?\n\s*OK\s*$", tests.stderr, re.S)
    checks["python_311_full_suite_pass"] = (
        version.stdout.startswith("Python 3.11.") and tests.returncode == 0
        and bool(match) and int(match.group(1)) >= 113)
    (OUT / "V7_FULL_UNITTEST_EXIT.json").write_text(json.dumps({
        "command": ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v",
        "python_version": version.stdout.strip(), "exit_code": tests.returncode,
        "test_count": int(match.group(1)) if match else None}, indent=2) + "\n", encoding="utf-8")
    result = {"source_commit": source_commit, "offline_gate_pass": all(checks.values()),
              "checks": checks, "test_count": int(match.group(1)) if match else None,
              "source_sha256": {name: sha(ROOT / name) for name in SOURCE_FILES},
              "local_proposal_sha256": provenance["local_v7_report_sha256"],
              "handoff_sha256": provenance["researcher_handoff_sha256"],
              "prompt_sha256": {cell: {actor: prompt_sha256(actor, CellConfig.for_cell(cell))
                                      for actor in AGENTS} for cell in "ABCD"},
              "tool_schema_sha256": sha(ROOT / "v7_approved_interface/tools.json"),
              "actual_model_template_compatibility": "PENDING_ISOLATED_REAL_SMOKE",
              "smoke_not_data_required_before_study": True,
              "provenance": "OFFLINE VALIDATION; NO PROVIDER CALL"}
    (OUT / "V7_OFFLINE_READINESS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"source_commit": source_commit, "checks": checks,
                      "test_count": result["test_count"], "offline_gate_pass": result["offline_gate_pass"]},
                     indent=2, sort_keys=True))
    if not result["offline_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
