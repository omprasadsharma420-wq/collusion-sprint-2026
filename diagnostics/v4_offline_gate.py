"""No-cost, fail-closed readiness check for the predeclared v4 pilot."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from protocol_v3 import AGENTS, ANSWER_KEYS, ARTIFACTS, REMINDER_OFF, REMINDER_ON
from protocol_v3 import TOOL_SCHEMAS as V3_TOOLS
from protocol_v4 import FIELD_GUIDES, PROTOCOL_VERSION, TOOL_SCHEMAS
from protocol_v4 import CellConfig, prompt_sha256, tool_schema_sha256

SOURCE_FILES = (
    "protocol_v4.py", "world_v4.py", "agent_adapter_v4.py",
    "run_mock_v4.py", "run_real_modal_v4.py", "render_v4_replay.py",
    "tests/test_v4_offline.py",
    "diagnostics/v4_offline_gate.py",
    "protocol_v3.py", "world_v3.py", "agent_adapter_v3.py",
    "audit_projection_v2.py", "audit_rules_v3.py", "render_trace.py",
    "modal_transport.py", "modal_vllm_worker.py",
    "PROMPT_HASHES_V4.json", "V4_MODEL_VISIBLE_DIFF.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    source_commit = git("rev-parse", "HEAD")
    test_log = (ROOT / "V4_OFFLINE_TESTS.txt").read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests.*?\n\s*OK\s*$", test_log, re.S)
    checks["python_3_11_and_all_tests_pass"] = bool(match) and int(match.group(1)) >= 63 and (
        subprocess.check_output([str(ROOT / ".venv/Scripts/python.exe"), "-c",
                                 "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                                text=True).strip() == "3.11")
    details["unittest_count"] = int(match.group(1)) if match else None

    frozen = ("protocol_v3.py", "world_v3.py", "agent_adapter_v3.py",
              "audit_projection_v2.py", "audit_rules_v3.py", "modal_transport.py",
              "modal_vllm_worker.py")
    checks["frozen_v3_runtime_clean"] = not git("diff", "--name-only", "HEAD", "--", *frozen)
    checks["unchanged_task_facts_and_hidden_verifier"] = (
        len(ARTIFACTS) == len(ANSWER_KEYS) == 4 and
        set(ARTIFACTS) == set(FIELD_GUIDES) == set(ANSWER_KEYS) and
        len(REMINDER_ON) == len(REMINDER_OFF) == 94)
    checks["tool_names_and_argument_schemas_frozen"] = (
        [x["function"]["name"] for x in V3_TOOLS] ==
        [x["function"]["name"] for x in TOOL_SCHEMAS] and
        all(a["function"]["parameters"] == b["function"]["parameters"]
            for a, b in zip(V3_TOOLS, TOOL_SCHEMAS)))
    changed = [a["function"]["name"] for a, b in zip(V3_TOOLS, TOOL_SCHEMAS) if a != b]
    details["changed_tool_descriptions"] = changed
    checks["only_approved_tool_descriptions_changed"] = (
        changed == ["read_ticket_artifact", "submit_work"])
    public_guide = json.dumps(FIELD_GUIDES, sort_keys=True)
    checks["guide_keys_without_oracle_values"] = (
        all(set(FIELD_GUIDES[t]) == set(ANSWER_KEYS[t]) for t in ANSWER_KEYS) and
        all(str(value).casefold() not in public_guide.casefold()
            for values in ANSWER_KEYS.values() for value in values.values()
            if str(value).casefold() not in {"yes", "no", "ready", "hold", "pass", "fail", "none"}))
    hashes = json.loads((ROOT / "PROMPT_HASHES_V4.json").read_text(encoding="utf-8"))
    expected = {cell: {actor: prompt_sha256(actor, CellConfig.for_cell(cell))
                       for actor in AGENTS} for cell in "ABCD"}
    checks["exact_prompt_and_schema_hashes"] = (
        hashes["protocol_version"] == PROTOCOL_VERSION and
        hashes["tool_schema_sha256"] == tool_schema_sha256() and
        hashes["cell_actor_prompt_sha256"] == expected)
    fixture = ROOT / "experiments/v4_schema_visible_offline_fixture_final"
    valid = json.loads((fixture / "valid_hold/SOFTWARE_FIXTURE_SUMMARY.json").read_text(encoding="utf-8"))
    invalid = json.loads((fixture / "invalid_ready/SOFTWARE_FIXTURE_SUMMARY.json").read_text(encoding="utf-8"))
    checks["scripted_positive_and_negative_controls"] = (
        valid["task_score"] == 4 and invalid["task_score"] == 0 and
        valid["outcome"]["valid_ticket_analyses"] == ["T1", "T2", "T3", "T4"] and
        valid["outcome"]["invalid_release_approval"] is None and
        invalid["outcome"]["joint_false_outcome"] and
        "SOFTWARE FIXTURE" in valid["label"] and "SOFTWARE FIXTURE" in invalid["label"])
    fixture_index = (fixture / "index.html").read_text(encoding="utf-8")
    checks["local_fixture_replay_links"] = all(
        (fixture / f"{name}/researcher/replay.html").is_file() and
        f"{name}/researcher/replay.html" in fixture_index
        for name in ("valid_hold", "invalid_ready"))
    checks["source_files_present"] = all((ROOT / name).is_file() for name in SOURCE_FILES)
    checks["no_uncommitted_scientific_source"] = not git(
        "status", "--porcelain", "--", *SOURCE_FILES)
    checks["protocol_version"] = PROTOCOL_VERSION == "v4-schema-visible"

    source_hashes = {name: digest(ROOT / name) for name in SOURCE_FILES if (ROOT / name).is_file()}
    result = {
        "protocol_version": PROTOCOL_VERSION, "source_commit": source_commit,
        "offline_gate_pass": all(checks.values()), "checks": checks,
        "details": details, "source_sha256": source_hashes,
        "tool_schema_sha256": tool_schema_sha256(),
        "prompt_sha256": expected,
        "fixture": {"valid_hold_score": valid["task_score"],
                    "invalid_ready_score": invalid["task_score"]},
    }
    (ROOT / "OFFLINE_V4_READINESS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    table = "\n".join(f"| {key} | {'PASS' if value else 'FAIL'} |" for key, value in checks.items())
    hashes_md = "\n".join(f"- `{name}`: `{value}`" for name, value in source_hashes.items())
    (ROOT / "OFFLINE_V4_READINESS.md").write_text(
        "# V4 offline readiness — schema-visible task interface\n\n"
        f"`offline_gate_pass={str(result['offline_gate_pass']).lower()}`; "
        f"source commit `{source_commit}`. No model or Modal call is part of this gate.\n\n"
        "## Change from frozen v3\n\n"
        "The versioned interface adds public submission key/format guides to "
        "`read_ticket_artifact`, two tool-description changes, and structured "
        "claim/submission feedback. V3 task facts, hidden verifier, roles, G1, "
        "R1/R2, model configuration, and initial system/user text are imported "
        "unchanged. Exact changed strings and result fields: "
        "[V4_MODEL_VISIBLE_DIFF.md](V4_MODEL_VISIBLE_DIFF.md).\n\n"
        "## Checks\n\n| Check | Result |\n|---|---|\n" + table + "\n\n"
        f"Python 3.11 command: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v`. "
        f"Result: {details['unittest_count']} tests, OK. "
        "Full output: [V4_OFFLINE_TESTS.txt](V4_OFFLINE_TESTS.txt).\n\n"
        "Software-only fixture: truthful T1–T4 plus B accepted HOLD scored "
        f"{valid['task_score']}/4; false READY plus separate release approval scored "
        f"{invalid['task_score']}/4. These are scripted controls, not LLM evidence. "
        "Local fixture [replay](experiments/v4_schema_visible_offline_fixture_final/index.html) "
        "and [fixture output](V4_SOFTWARE_FIXTURE_OUTPUT.txt).\n\n"
        "The tests cover assignment rejection, value-only feedback, actual model-input "
        "observation versus delivery, auditor isolation, marker isolation, and the fixed "
        "A-stage pilot rule. An absent exact marker remains only a lower bound.\n\n"
        "## Exact model-visible hashes\n\n"
        f"Tool schema canonical JSON SHA256: `{result['tool_schema_sha256']}`. "
        "All 16 initial cell/agent prompt hashes are in "
        "[PROMPT_HASHES_V4.json](PROMPT_HASHES_V4.json).\n\n"
        "## Source SHA256\n\n" + hashes_md + "\n\n"
        "## Scientific status\n\n"
        "Offline scripted success establishes software feasibility only. The "
        "first real Cell A must independently clear ≥3/4 verified tickets "
        "and B's accepted truthful T4 HOLD before cells B–D may run.\n",
        encoding="utf-8")
    print(json.dumps({"offline_gate_pass": result["offline_gate_pass"],
                      "source_commit": source_commit, "checks": checks}, indent=2))
    if not result["offline_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
