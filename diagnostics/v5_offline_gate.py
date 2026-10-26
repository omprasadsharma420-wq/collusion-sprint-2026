"""Fail-closed, no-cost v5 horizon-only readiness check."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from protocol_v3 import AGENTS, ANSWER_KEYS, ARTIFACTS
from protocol_v4 import CellConfig, TOOL_SCHEMAS as V4_TOOLS
from protocol_v4 import prompt_sha256 as v4_prompt_sha256
from protocol_v5 import PROTOCOL_VERSION, TOOL_SCHEMAS, prompt_sha256, tool_schema_sha256
from run_real_modal_v5 import (MAX_GPU_WALL_SECONDS, MAX_RESPONSES_PER_AGENT,
                                MAX_STUDY_CALLS, MAX_TOTAL_CALLS)

SOURCE_FILES = (
    "protocol_v5.py", "world_v5.py", "agent_adapter_v5.py",
    "run_real_modal_v5.py", "run_mock_v5.py", "render_v5_replay.py",
    "tests/test_v5_offline.py", "diagnostics/v5_offline_gate.py",
    "PROMPT_HASHES_V5.json", "V5_HORIZON_DIFF.md", "V5_RUNNER_DIFF.patch",
    "protocol_v4.py", "world_v4.py", "agent_adapter_v4.py",
    "run_real_modal_v4.py", "run_mock_v4.py", "render_v4_replay.py",
    "protocol_v3.py", "world_v3.py", "agent_adapter_v3.py",
    "audit_projection_v2.py", "audit_rules_v3.py",
    "modal_transport.py", "modal_vllm_worker.py",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_v5(source: str, *, fixture: bool = False) -> str:
    result = source.replace("v5", "v4").replace("V5", "V4")
    result = result.replace("v4-longer-horizon", "v4-schema-visible")
    result = result.replace("real_v4_longer_horizon", "real_v4_schema_visible")
    result = result.replace("MAX_RESPONSES_PER_AGENT = 24", "MAX_RESPONSES_PER_AGENT = 16")
    result = result.replace("MAX_STUDY_CALLS = 384", "MAX_STUDY_CALLS = 256")
    result = result.replace("MAX_TOTAL_CALLS = 385", "MAX_TOTAL_CALLS = 257")
    if fixture:
        result = result.replace("v4_longer_horizon_offline_fixture",
                                "v4_schema_visible_offline_fixture")
        result = result.replace("tool_call_cap=24", "tool_call_cap=16")
    return result


def main() -> None:
    checks: dict[str, bool] = {}
    source_commit = git("rev-parse", "HEAD")
    stage0 = json.loads((ROOT / "experiments/real_v4_schema_visible_20261025T160532Z/"
                         "researcher/v4_a_diagnosis/INTEGRITY_GATE.json").read_text())
    checks["v4_stage0_integrity_passed"] = stage0["stage0_integrity_gate_pass"] is True
    checks["only_cap_in_runner_after_version_normalization"] = (
        normalize_v5((ROOT / "run_real_modal_v5.py").read_text(encoding="utf-8")) ==
        (ROOT / "run_real_modal_v4.py").read_text(encoding="utf-8"))
    checks["same_scripted_controls_after_cap_normalization"] = (
        normalize_v5((ROOT / "run_mock_v5.py").read_text(encoding="utf-8"), fixture=True) ==
        (ROOT / "run_mock_v4.py").read_text(encoding="utf-8"))
    checks["same_replay_logic_after_version_normalization"] = (
        normalize_v5((ROOT / "render_v5_replay.py").read_text(encoding="utf-8")) ==
        (ROOT / "render_v4_replay.py").read_text(encoding="utf-8"))
    checks["bounded_horizon_only"] = (
        MAX_RESPONSES_PER_AGENT == 24 and MAX_STUDY_CALLS == 384 and
        MAX_TOTAL_CALLS == 385 and MAX_GPU_WALL_SECONDS == 90 * 60)
    hashes = json.loads((ROOT / "PROMPT_HASHES_V5.json").read_text(encoding="utf-8"))
    expected = {cell: {actor: prompt_sha256(actor, CellConfig.for_cell(cell))
                       for actor in AGENTS} for cell in "ABCD"}
    checks["identical_model_visible_prompts_and_tools"] = (
        PROTOCOL_VERSION == "v5-longer-horizon" and
        TOOL_SCHEMAS == V4_TOOLS and
        hashes["cell_actor_prompt_sha256"] == expected and
        hashes["tool_schema_sha256"] == tool_schema_sha256() and
        all(expected[cell][actor] == v4_prompt_sha256(actor, CellConfig.for_cell(cell))
            for cell in "ABCD" for actor in AGENTS))
    checks["task_facts_and_verifier_unchanged"] = (
        set(ARTIFACTS) == set(ANSWER_KEYS) == {"T1", "T2", "T3", "T4"} and
        not git("diff", "--name-only", "HEAD", "--", "protocol_v3.py", "world_v3.py",
                "protocol_v4.py", "world_v4.py", "audit_rules_v3.py", "modal_transport.py"))
    test_log = (ROOT / "V5_OFFLINE_TESTS.txt").read_text(encoding="utf-8-sig")
    match = re.search(r"Ran (\d+) tests.*?\n\s*OK\s*$", test_log, re.S)
    checks["python_3_11_and_69_tests_pass"] = bool(match) and int(match.group(1)) >= 69 and (
        subprocess.check_output([str(ROOT / ".venv/Scripts/python.exe"), "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            text=True).strip() == "3.11")
    fixture = ROOT / "experiments/v5_longer_horizon_offline_fixture"
    valid = json.loads((fixture / "valid_hold/SOFTWARE_FIXTURE_SUMMARY.json").read_text())
    invalid = json.loads((fixture / "invalid_ready/SOFTWARE_FIXTURE_SUMMARY.json").read_text())
    checks["scripted_controls_4_and_0"] = (
        valid["task_score"] == 4 and invalid["task_score"] == 0 and
        "SOFTWARE FIXTURE" in valid["label"] and "SOFTWARE FIXTURE" in invalid["label"])
    checks["local_fixture_replay_links"] = all(
        (fixture / f"{name}/researcher/replay.html").is_file() and
        f"{name}/researcher/replay.html" in (fixture / "index.html").read_text()
        for name in ("valid_hold", "invalid_ready"))
    checks["source_files_present_and_committed"] = (
        all((ROOT / name).is_file() for name in SOURCE_FILES) and
        not git("status", "--porcelain", "--", *SOURCE_FILES))
    source_hashes = {name: sha(ROOT / name) for name in SOURCE_FILES}
    result = {"protocol_version": PROTOCOL_VERSION, "source_commit": source_commit,
              "offline_gate_pass": all(checks.values()), "checks": checks,
              "source_sha256": source_hashes, "prompt_sha256": expected,
              "tool_schema_sha256": tool_schema_sha256(),
              "fixture": {"valid_hold_score": valid["task_score"],
                          "invalid_ready_score": invalid["task_score"]},
              "test_count": int(match.group(1)) if match else None}
    (ROOT / "OFFLINE_V5_READINESS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = "\n".join(f"| {name} | {'PASS' if value else 'FAIL'} |"
                     for name, value in checks.items())
    source_rows = "\n".join(f"- `{name}`: `{digest}`" for name, digest in source_hashes.items())
    (ROOT / "OFFLINE_V5_READINESS.md").write_text(
        "# V5-longer-horizon offline readiness\n\n"
        f"`offline_gate_pass={str(result['offline_gate_pass']).lower()}`. "
        f"Source commit `{source_commit}`. No model or GPU call was made by this gate.\n\n"
        "The [v4 causal diagnosis](experiments/real_v4_schema_visible_20261025T160532Z/"
        "researcher/V4_CELL_A_CAUSAL_DIAGNOSIS.md) passed the prerequisite integrity gate. "
        "The sole prospective treatment is 16→24 maximum responses per agent. "
        "Exact [horizon diff](V5_HORIZON_DIFF.md) and [runner patch](V5_RUNNER_DIFF.patch). "
        "All initial model-visible prompt and tool bytes match v4 exactly.\n\n"
        "| Check | Result |\n|---|---|\n" + rows + "\n\n"
        "Command: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v`. "
        f"Result: {result['test_count']} tests, OK; [full log](V5_OFFLINE_TESTS.txt). "
        "The scripted [v5 control replay](experiments/v5_longer_horizon_offline_fixture/"
        "index.html) scores valid HOLD 4/4 and invalid READY 0/4; it is SOFTWARE "
        "FIXTURE only, not model behavior.\n\n"
        f"Tool schema SHA256: `{tool_schema_sha256()}`. "
        "[All 16 prompt hashes](PROMPT_HASHES_V5.json) are identical to v4.\n\n"
        "## Source SHA256\n\n" + source_rows + "\n\n"
        "If this gate passes, only one fresh real Cell A may start. B/C/D depend on "
        "the unchanged ≥3/4 plus accepted truthful T4 HOLD pilot gate.\n",
        encoding="utf-8")
    print(json.dumps({"offline_gate_pass": result["offline_gate_pass"],
                      "source_commit": source_commit, "checks": checks}, indent=2))
    if not result["offline_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
