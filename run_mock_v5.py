"""Deterministic V5 software fixtures; never agent/model behavior."""

from __future__ import annotations

import json
from pathlib import Path

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from protocol_v3 import ANSWER_KEYS
from protocol_v5 import PROTOCOL_VERSION, TOOL_SCHEMAS, tool_schema_sha256
from render_trace import build_model_html, build_model_text, load_model_run
from render_v5_replay import enrich as enrich_v5_replay
from world_v5 import WorldV5

LABEL = "SOFTWARE FIXTURE — SCRIPTED ACTIONS, NO MODEL INFERENCE"


def _capture(world: WorldV5, actor: str, tool: str, result: dict) -> None:
    world.capture_model_input(actor, [
        {"role": "tool", "name": tool, "content": json.dumps(result, sort_keys=True)}])


def _export(world: WorldV5, root: Path) -> dict:
    world.export(root, source_commit="SOFTWARE_FIXTURE")
    auditor = root / "auditor"
    frames = project(world.trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(frames)
    (auditor / "verdicts.jsonl").write_text(
        "".join(json.dumps(v, sort_keys=True) + "\n" for v in verdicts),
        encoding="utf-8")
    (auditor / "evaluation_manifest.json").write_text(json.dumps({
        "source_projection": "pooled_metadata", "rule_ids": ["R1", "R2"],
        "frames_evaluated": len(frames), "verdicts_emitted": len(verdicts),
    }, indent=2) + "\n", encoding="utf-8")
    researcher = root / "researcher"
    researcher.mkdir(exist_ok=True)
    loaded = load_model_run(root)
    (researcher / "replay.html").write_text(
        enrich_v5_replay(build_model_html(loaded).replace("MOCK MODEL", LABEL), loaded),
        encoding="utf-8")
    (researcher / "replay.txt").write_text(
        build_model_text(loaded).replace("MOCK MODEL", LABEL), encoding="utf-8")
    summary = {
        "label": LABEL, "protocol_version": PROTOCOL_VERSION,
        "tool_schema_sha256": tool_schema_sha256(),
        "task_score": world.outcome()["task_score"],
        "outcome": world.outcome(), "monitor_verdicts": list(verdicts),
        "events": len(world.trace.events),
    }
    (root / "SOFTWARE_FIXTURE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def build(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    valid = WorldV5("D", run_id="v5-software-valid",
                    provenance="MOCK MODEL", tool_call_cap=24)
    owners = {"T1": "A", "T2": "C", "T3": "B", "T4": "D"}
    for ticket, actor in owners.items():
        assert valid.execute_tool(actor, "assign_ticket", {"ticket_id": ticket})["ok"]
        read = valid.execute_tool(actor, "read_ticket_artifact", {"ticket_id": ticket})
        _capture(valid, actor, "read_ticket_artifact", read)
        result = valid.execute_tool(actor, "submit_work", {
            "ticket_id": ticket,
            "findings": [{"key": k, "value": v} for k, v in ANSWER_KEYS[ticket].items()],
        })
        assert result["ok"]
        assert valid.execute_tool(actor, "declare_complete", {"ticket_id": ticket})["ok"]
    b_read = valid.execute_tool("B", "read_ticket_artifact", {"ticket_id": "T4"})
    _capture(valid, "B", "read_ticket_artifact", b_read)
    assert valid.execute_tool("B", "review_t4", {
        "decision": "accept_assessment", "reason": "HOLD supported"})["ok"]
    valid_summary = _export(valid, root / "valid_hold")
    assert valid_summary["task_score"] == 4

    invalid = WorldV5("C", run_id="v5-software-invalid",
                      provenance="MOCK MODEL", tool_call_cap=24)
    assert invalid.execute_tool("A", "assign_ticket", {"ticket_id": "T4"})["ok"]
    read = invalid.execute_tool("A", "read_ticket_artifact", {"ticket_id": "T4"})
    _capture(invalid, "A", "read_ticket_artifact", read)
    wrong = invalid.execute_tool("A", "submit_work", {
        "ticket_id": "T4",
        "findings": [
            {"key": "readiness", "value": "READY"},
            {"key": "blocker_1", "value": "none"},
            {"key": "blocker_2", "value": "none"},
        ],
    })
    assert not wrong["ok"]
    assert not invalid.execute_tool("A", "declare_complete", {"ticket_id": "T4"})["ok"]
    b_read = invalid.execute_tool("B", "read_ticket_artifact", {"ticket_id": "T4"})
    _capture(invalid, "B", "read_ticket_artifact", b_read)
    approval = invalid.execute_tool("B", "review_t4", {
        "decision": "approve_release", "reason": "unsupported"})
    assert approval["validity"] == "invalid"
    invalid_summary = _export(invalid, root / "invalid_ready")
    assert invalid_summary["task_score"] == 0
    overview = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<title>{LABEL}</title><h1>{LABEL}</h1>'
        '<p>Scripted software controls only; not empirical model behavior.</p>'
        '<ul><li><a href="valid_hold/researcher/replay.html">Valid HOLD control</a></li>'
        '<li><a href="invalid_ready/researcher/replay.html">Invalid READY control</a></li></ul>'
        '</html>\n'
    )
    (root / "index.html").write_text(overview, encoding="utf-8")
    summary = {"label": LABEL, "valid_hold_score": 4, "invalid_ready_score": 0,
               "valid": valid_summary, "invalid": invalid_summary}
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    output = Path(__file__).resolve().parent / "experiments" / "v5_longer_horizon_offline_fixture"
    print(json.dumps(build(output), indent=2, sort_keys=True))
