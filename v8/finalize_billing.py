"""Offline aggregation of saved official Modal app/usage/billing JSON."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apps", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--app-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    apps = {item["app_id"]: item for item in load(args.apps)}
    report = load(args.report)
    summary = load(args.summary)
    by_app = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    for row in report:
        if row["object_id"] in args.app_id:
            by_app[row["object_id"]][row["resource"]] += Decimal(row["cost"])
    per_app = {}
    for app_id in args.app_id:
        if app_id not in apps or apps[app_id]["state"] != "stopped" or str(
                apps[app_id]["tasks"]) != "0":
            raise RuntimeError(f"App not verified stopped with zero tasks: {app_id}")
        resources = by_app[app_id]
        if not {"L4", "CPU", "Memory"} <= set(resources):
            raise RuntimeError(f"Missing official resource line for app {app_id}")
        per_app[app_id] = {
            "stop_verification": apps[app_id],
            "app_resource_metered_usd": {key: str(value) for key, value in
                                          sorted(resources.items())},
            "app_total_metered_usd": str(sum(resources.values(), Decimal("0"))),
            "per_app_billed_usd": "NOT_REPORTED_BY_MODAL",
        }
    result = {
        "apps": per_app,
        "all_apps_verified_stopped_zero_tasks": True,
        "all_v8_apps_total_metered_usd": str(sum(
            (Decimal(v["app_total_metered_usd"]) for v in per_app.values()),
            Decimal("0"))),
        "workspace_month_metered_usd_at_read": summary["metered_cost"],
        "workspace_month_billed_usd_at_read": summary["billed_cost"],
        "per_app_billed_usd": "NOT_REPORTED_BY_MODAL",
        "billing_scope_note": "App resource lines are app-specific metered usage. Workspace billed amount includes all apps and credits; no per-app billed amount is reported. Usage may settle.",
        "source_commands": ["modal app list --json", "modal billing report --for today --show-resources --json",
                            "modal billing summary --json"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
