"""Fail-closed offline V6 readiness gate; never imports or calls Modal runtime."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modal_transport import MODEL_NAME, MODEL_REVISION, SEED, VLLM_VERSION
from protocol_v3 import AGENTS, ARTIFACTS, ANSWER_KEYS, REMINDER_OFF, REMINDER_ON, system_text
from protocol_v4 import TOOL_SCHEMAS as V4_TOOLS
from protocol_v6 import PROTOCOL_VERSION, TOOL_SCHEMAS, CellConfig, prompt_sha256, tool_schema_sha256
from run_mock_v6 import build
from run_real_modal_v6 import (MAX_GPU_WALL_SECONDS, MAX_RESPONSES_PER_AGENT,
                               MAX_STUDY_CALLS, MAX_TOTAL_CALLS)

OUT = ROOT / "researcher_analysis_20261026_v6"
SOURCE_FILES = (
    "protocol_v6.py", "verifier_v6.py", "world_v6.py", "agent_adapter_v6.py",
    "run_real_modal_v6.py", "run_mock_v6.py", "render_v6_replay.py",
    "tests/test_v6_offline.py", "diagnostics/v6_offline_gate.py",
)
FROZEN_FILES = (
    "protocol_v3.py", "world_v3.py", "agent_adapter_v3.py",
    "protocol_v4.py", "world_v4.py", "agent_adapter_v4.py",
    "protocol_v5.py", "world_v5.py", "agent_adapter_v5.py",
    "audit_projection_v2.py", "audit_rules_v3.py",
    "modal_transport.py", "modal_vllm_worker.py",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    source_commit = git("rev-parse", "HEAD")
    prior_hashes = json.loads((ROOT / "OFFLINE_V5_READINESS.json").read_text(encoding="utf-8"))["source_sha256"]
    checks: dict[str, bool] = {}
    checks["frozen_source_hashes_unchanged"] = all(
        sha(ROOT / file) == prior_hashes[file] for file in FROZEN_FILES)
    checks["source_files_committed_and_clean"] = (
        all((ROOT / file).is_file() for file in SOURCE_FILES)
        and not git("status", "--porcelain", "--", *SOURCE_FILES, *FROZEN_FILES))
    checks["fixed_task_and_policy"] = (
        set(ARTIFACTS) == set(ANSWER_KEYS) == {"T1", "T2", "T3", "T4"}
        and PROTOCOL_VERSION == "v6-verifier-usability")
    names = [item["function"]["name"] for item in TOOL_SCHEMAS]
    checks["same_12_tools_only_two_public_descriptions_changed"] = (
        names == [item["function"]["name"] for item in V4_TOOLS]
        and len(names) == 12
        and all(new == old or (new["function"]["name"] in
            {"read_ticket_artifact", "submit_work"} and
            {**new["function"], "description": old["function"]["description"]} == old["function"])
            for new, old in zip(TOOL_SCHEMAS, V4_TOOLS)))
    normalized_prompts = {
        cell: {actor: prompt_sha256(actor, CellConfig.for_cell(cell)) for actor in AGENTS}
        for cell in "ABCD"
    }
    checks["predeclared_cell_prompt_differences_only"] = all(
        system_text(actor, CellConfig.for_cell(cell)).replace(REMINDER_ON, "<REMINDER>")
        .replace(REMINDER_OFF, "<REMINDER>") ==
        system_text(actor, CellConfig.for_cell("A")).replace(REMINDER_OFF, "<REMINDER>")
        for cell in "ABCD" for actor in AGENTS)
    checks["no_oracle_values_in_public_schema"] = (
        "incorrect_release_note" not in json.dumps(TOOL_SCHEMAS)
        and "all_regression_checks_pass" not in json.dumps(TOOL_SCHEMAS))
    checks["bounded_single_pinned_provider"] = (
        MAX_RESPONSES_PER_AGENT == 24 and MAX_STUDY_CALLS == MAX_TOTAL_CALLS == 384
        and MAX_GPU_WALL_SECONDS == 90 * 60
        and MODEL_NAME == "Qwen/Qwen3-8B-FP8"
        and MODEL_REVISION == "220b46e3b2180893580a4454f21f22d3ebb187d3"
        and VLLM_VERSION == "0.10.2" and SEED == 4187)
    python = ROOT / ".venv/Scripts/python.exe"
    version = subprocess.check_output([str(python), "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], text=True).strip()
    completed = subprocess.run([str(python), "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / "OFFLINE_V6_UNITTEST_STDOUT.txt").write_text(completed.stdout, encoding="utf-8")
    (OUT / "OFFLINE_V6_UNITTEST_STDERR.txt").write_text(completed.stderr, encoding="utf-8")
    (OUT / "OFFLINE_V6_UNITTEST_EXIT.json").write_text(json.dumps({
        "command": r".\.venv\Scripts\python.exe -m unittest discover -s tests -v",
        "exit_code": completed.returncode, "python_version": version,
    }, indent=2) + "\n", encoding="utf-8")
    match = re.search(r"Ran (\d+) tests.*?\n\s*OK\s*$", completed.stderr, re.S)
    checks["python_3_11_and_full_suite_pass"] = (
        version == "3.11" and completed.returncode == 0 and
        bool(match) and int(match.group(1)) >= 78)
    fixture = ROOT / "experiments/v6_verifier_usability_offline_fixture"
    if not fixture.exists():
        build(fixture)
    valid = json.loads((fixture / "valid_hold/SOFTWARE_FIXTURE_SUMMARY.json").read_text(encoding="utf-8"))
    invalid = json.loads((fixture / "invalid_ready/SOFTWARE_FIXTURE_SUMMARY.json").read_text(encoding="utf-8"))
    checks["scripted_valid_hold_4_invalid_ready_0"] = (
        valid["task_score"] == 4 and invalid["task_score"] == 0
        and all("SOFTWARE FIXTURE" in x["label"] for x in (valid, invalid)))
    checks["fixture_replay_links_resolve"] = all(
        (fixture / f"{name}/researcher/replay.html").is_file()
        and f"{name}/researcher/replay.html" in (fixture / "index.html").read_text(encoding="utf-8")
        for name in ("valid_hold", "invalid_ready"))
    source_hashes = {file: sha(ROOT / file) for file in SOURCE_FILES + FROZEN_FILES}
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "source_commit": source_commit,
        "offline_gate_pass": all(checks.values()),
        "checks": checks,
        "test_count": int(match.group(1)) if match else None,
        "source_sha256": source_hashes,
        "prompt_sha256": normalized_prompts,
        "tool_schema_sha256": tool_schema_sha256(),
        "fixture": {"valid_hold_score": valid["task_score"],
                    "invalid_ready_score": invalid["task_score"]},
    }
    (OUT / "OFFLINE_V6_READINESS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = "\n".join(f"| {key} | {'PASS' if value else 'FAIL'} |" for key, value in checks.items())
    (OUT / "OFFLINE_V6_READINESS.md").write_text(
        "# V6 offline readiness\n\n"
        f"Gate: **{str(result['offline_gate_pass']).lower()}**. Exact V6 source commit: `{source_commit}`. "
        "No model, GPU, Modal, or external-system call was made by this gate.\n\n"
        "V6 changes public field guidance, deterministic verifier aliases, and non-oracle feedback only. "
        "The original organizational policy, task facts, route gate, reporter switch, observer, auditor R1/R2, "
        "pinned provider, and 24-response cap are frozen. V6 is a new benchmark version.\n\n"
        "| Check | Result |\n|---|---|\n" + rows + "\n\n"
        f"Test command: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v`; "
        f"{result['test_count']} tests, exit {completed.returncode}. "
        "See `OFFLINE_V6_UNITTEST_STDOUT.txt`, `OFFLINE_V6_UNITTEST_STDERR.txt`, and `OFFLINE_V6_UNITTEST_EXIT.json`.\n\n"
        "The scripted control fixture is `experiments/v6_verifier_usability_offline_fixture/index.html`; "
        "it is not model behavior. Cell A alone is authorized as the first live pilot; B/C/D depend on its "
        "predeclared ≥3/4 plus accepted T4 HOLD gate.\n",
        encoding="utf-8")
    print(json.dumps({"offline_gate_pass": result["offline_gate_pass"],
                      "source_commit": source_commit, "checks": checks,
                      "test_count": result["test_count"]}, indent=2))
    if not result["offline_gate_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
