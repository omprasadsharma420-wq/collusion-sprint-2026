"""Offline aggregation of saved read-only Modal CLI output; no Modal calls."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ID = "ap-4WUosm4pBop2KNHb7q8Qpc"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    run = args.run_root.resolve()
    if not run.is_relative_to(ROOT / "experiments") or not run.name.startswith("real_v6_verifier_usability_"):
        raise ValueError("Expected V6 saved run")
    apps = load(run / "MODAL_STOP_VERIFICATION.json")
    rows = [row for row in apps if row["app_id"] == APP_ID]
    assert len(rows) == 1 and rows[0]["state"] == "stopped" and rows[0]["tasks"] == "0"
    report = load(run / "MODAL_BILLING_REPORT_RAW.json")
    resources = {row["resource"]: Decimal(row["cost"]) for row in report if row["object_id"] == APP_ID}
    assert {"L4", "CPU", "Memory"} <= set(resources)
    summary = load(run / "MODAL_BILLING_SUMMARY_RAW.json")
    result = {
        "app_id": APP_ID,
        "app_stop_verification": rows[0],
        "app_resource_metered_usd": {key: str(value) for key, value in sorted(resources.items())},
        "app_metered_usd": str(sum(resources.values(), Decimal("0"))),
        "workspace_october_metered_usd_at_read": summary["metered_cost"],
        "workspace_october_billed_usd_at_read": summary["billed_cost"],
        "per_app_billed_usd": "NOT_REPORTED_BY_MODAL",
        "billing_scope_note": "App resource lines are metered. Workspace billed amount is after credits and includes all apps; it is not an app-specific bill.",
        "source_commands": [
            "python -m modal app list --json",
            "python -m modal billing summary --for 2026-10 --json",
            "python -m modal billing report --start 2026-10-25 --end 2026-10-26 --resolution h --show-resources --json",
        ],
    }
    (run / "MODAL_COST_AND_STOP_VERIFICATION.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
