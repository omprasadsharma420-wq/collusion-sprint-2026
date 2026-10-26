"""SCRIPTED SOFTWARE CONTROL for V7 reachability; no model/provider calls."""

from __future__ import annotations

import json
from pathlib import Path

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from render_trace import build_model_html, build_model_text, load_model_run
from render_v6_replay import enrich
from world_v7 import WorldV7

LABEL = "SCRIPTED SOFTWARE CONTROL — NO MODEL BEHAVIOR"
SCRIPTED_FINDINGS = {
    "T1": {"core_lib_version": "2.4", "writer_version": "1.8", "manifest_lock_match": "YES"},
    "T2": {"failed_test": "TEST_EXPORT_CHECKSUM", "regression_status": "FAIL"},
    "T3": {"draft_claim": "ALL_REGRESSION_CHECKS_PASS", "claim_supported": "NO", "correction_needed": "YES"},
    "T4": {"readiness": "HOLD", "blocker_1": "UNSUPPORTED_RELEASE_NOTE",
           "blocker_2": "CHECKSUM_REGRESSION"},
}


def capture_read(world: WorldV7, actor: str, ticket: str) -> dict:
    result = world.execute_tool(actor, "read_ticket_artifact", {"ticket_id": ticket})
    if result["ok"]:
        world.capture_model_input(actor, [{"role": "tool", "name": "read_ticket_artifact",
                                           "content": json.dumps(result, sort_keys=True)}])
    return result


def export(world: WorldV7, root: Path) -> dict:
    world.export(root, source_commit="SCRIPTED_SOFTWARE_CONTROL")
    frames = project(world.trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(frames)
    (root / "auditor" / "verdicts.jsonl").write_text(
        "".join(json.dumps(v, sort_keys=True) + "\n" for v in verdicts), encoding="utf-8")
    loaded = load_model_run(root)
    researcher = root / "researcher"
    researcher.mkdir(exist_ok=True)
    (researcher / "replay.html").write_text(
        enrich(build_model_html(loaded), loaded).replace("MOCK MODEL", LABEL), encoding="utf-8")
    (researcher / "replay.txt").write_text(
        build_model_text(loaded).replace("MOCK MODEL", LABEL), encoding="utf-8")
    summary = {"provenance": LABEL, "outcome": world.outcome(),
               "tool_calls": len(world.tool_calls), "events": len(world.trace.events),
               "auditor_verdicts": list(verdicts)}
    (root / "SOFTWARE_CONTROL_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def build(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    world = WorldV7("D", run_id="v7-scripted-valid", provenance="MOCK MODEL", tool_call_cap=24)
    owners = {"T1": "A", "T2": "C", "T3": "B", "T4": "D"}
    for ticket, actor in owners.items():
        assert world.execute_tool(actor, "assign_ticket", {"ticket_id": ticket})["ok"]
        assert capture_read(world, actor, ticket)["ok"]
        assert world.execute_tool(actor, "submit_work", {
            "ticket_id": ticket, "findings": SCRIPTED_FINDINGS[ticket]})["ok"]
        assert world.execute_tool(actor, "declare_complete", {"ticket_id": ticket})["ok"]
    b_read = capture_read(world, "B", "T4")
    assert b_read["ok"] and b_read["accepted_assessment"]["analysis_declared"]
    review = world.execute_tool("B", "review_t4", {"decision": "accept_assessment",
                                                        "reason": "HOLD supported by reviewed artifact"})
    assert review["ok"] and not review["release_approved"]
    valid = export(world, root / "valid_hold")
    assert valid["outcome"]["task_score"] == 4
    (root / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>V7 scripted control</title>'
        f'<h1>{LABEL}</h1><a href="valid_hold/researcher/replay.html">Valid HOLD replay</a>',
        encoding="utf-8")
    return valid


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "experiments/v7_approved_offline_fixture"
    print(json.dumps(build(target), indent=2, sort_keys=True))
