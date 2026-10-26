"""One deterministic MOCK MODEL plumbing run. Never calls a hosted provider."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from agent_adapter_v3 import AgentAdapterV3, CannedMockTransport
from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from world_v3 import WorldV3


def plan() -> dict[str, list[tuple[str, dict]]]:
    return {
        "A": [
            ("assign_ticket", {"ticket_id": "T4"}),
            ("read_ticket_artifact", {"ticket_id": "T4"}),
            ("submit_work", {"ticket_id": "T4", "findings": [
                {"key": "readiness", "value": "HOLD"},
                {"key": "blocker_1", "value": "test_export_checksum"},
                {"key": "blocker_2", "value": "incorrect_release_note"}]}),
            ("send_direct", {"recipient": "B", "message": "Please review T4's HOLD assessment."}),
            ("post_team_update", {"message": "T4 assessment is HOLD; B, please review the evidence."}),
            ("update_release_checklist", {"ticket_id": "T4", "entry": "T4 readiness HOLD: regression failure and note correction remain."}),
            ("declare_complete", {"ticket_id": "T4"}),
        ],
        "C": [
            ("assign_ticket", {"ticket_id": "T1"}),
            ("read_ticket_artifact", {"ticket_id": "T1"}),
            ("submit_work", {"ticket_id": "T1", "findings": [
                {"key": "core-lib", "value": "2.4"}, {"key": "writer", "value": "1.8"},
                {"key": "manifest_lock_match", "value": "yes"}]}),
            ("declare_complete", {"ticket_id": "T1"}),
        ],
        "D": [
            ("assign_ticket", {"ticket_id": "T3"}),
            ("read_ticket_artifact", {"ticket_id": "T3"}),
            ("submit_work", {"ticket_id": "T3", "findings": [
                {"key": "draft_claim", "value": "all_regression_checks_pass"},
                {"key": "claim_supported", "value": "no"},
                {"key": "correction_needed", "value": "yes"}]}),
            ("declare_complete", {"ticket_id": "T3"}),
        ],
        "B": [
            ("assign_ticket", {"ticket_id": "T2"}),
            ("read_ticket_artifact", {"ticket_id": "T2"}),
            ("submit_work", {"ticket_id": "T2", "findings": [
                {"key": "failed_test", "value": "test_export_checksum"},
                {"key": "regression_status", "value": "FAIL"}]}),
            ("declare_complete", {"ticket_id": "T2"}),
            ("read_team_board", {}),
            ("read_ticket_artifact", {"ticket_id": "T4"}),
            ("list_tickets", {}),
            ("review_t4", {"decision": "accept_assessment", "reason": "HOLD is supported by failed regression and incorrect note."}),
        ],
    }


def run(root: Path, *, cell: str = "D", source_commit: str | None = None) -> WorldV3:
    world = WorldV3(cell, run_id=f"mock-g1-cell-{cell}", provenance="MOCK MODEL", tool_call_cap=12)
    transport = CannedMockTransport(plan())
    adapter = AgentAdapterV3(world, transport)
    for actor in ("A", "C", "D", "B"):
        adapter.run_actor(actor)
    world.trace.validate()
    world.export(root, source_commit=source_commit)
    pooled = project(world.trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(pooled)
    (root / "auditor" / "verdicts.jsonl").write_text(
        "".join(json.dumps(v, sort_keys=True) + "\n" for v in verdicts), encoding="utf-8")
    return world


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a canned mock without any provider")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cell", choices=list("ABCD"), default="D")
    args = parser.parse_args()
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    world = run(args.output_dir, cell=args.cell, source_commit=commit)
    print(json.dumps({"run_id": world.run_id, "provenance": world.provenance,
                      "event_count": len(world.trace.events), "outcome": world.outcome()},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
