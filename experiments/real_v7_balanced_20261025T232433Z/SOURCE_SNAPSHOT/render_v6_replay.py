"""Researcher-only v6 replay additions. Never used as agent or auditor input."""

from __future__ import annotations

import html
import json
from typing import Any


STATUS_CLASSES = {
    "attempt": "attempt",
    "authorization_denial": "denied",
    "accepted_write": "accepted",
    "recipient_delivery": "delivered",
    "recipient_observation": "observed",
    "agent_discovery_report": "report",
    "evidence_verified": "evidence",
    "supervisor_decision": "decision",
}


def enrich(base_html: str, run: dict[str, Any]) -> str:
    """Add ordered, color-coded communication and separate report lanes."""
    event_rows: list[str] = []
    reports: list[str] = []
    record = run.get("run_record", {})
    counts = record.get("actor_response_counts", {})
    capacity = "".join(
        f"<li>{actor}: {counts.get(actor, 'NOT_RECORDED')}/24 responses; "
        f"{'AT_CAP' if counts.get(actor) == 24 else 'below cap or finalized'}</li>"
        for actor in "ABCD"
    )
    rule_status = []
    for rule in ("R1", "R2"):
        verdicts = [v for v in run["verdicts"] if v["rule_id"] == rule]
        status = ", ".join(v["verdict"].upper() for v in verdicts) if verdicts else "NOT_EVALUATED — no candidate frame"
        rule_status.append(f"<li>{rule}: {html.escape(status)}</li>")
    for event in run["events"]:
        kind = event["kind"]
        category = STATUS_CLASSES.get(kind, "other")
        data = event["data"]
        event_id = html.escape(event["event_id"])
        stamp = html.escape(run["timestamps"].get(event["event_id"], "TIME_NOT_CAPTURED"))
        actor = html.escape(event["actor"])
        detail = html.escape(json.dumps(data, sort_keys=True, ensure_ascii=False))
        row = (f'<div class="v6-event v6-{category}"><span class="v6-badge">'
               f'{html.escape(kind)}</span> <b>{event_id}</b> '
               f'<time>{stamp}</time> seq={event["seq"]} actor={actor}'
               f'<pre>{detail}</pre></div>')
        if kind == "agent_discovery_report":
            reports.append(row)
        else:
            event_rows.append(row)
    report_body = "".join(reports) or "<p>No agent discovery report was recorded.</p>"
    addition = (
        '<style>.v6-event{border-left:6px solid #8995a5;padding:.5rem 1rem;'
        'margin:.35rem 0;background:#f8fafc}.v6-event pre{margin:.3rem 0}.v6-badge{'
        'display:inline-block;background:#e4eaf0;padding:.15rem .4rem;font-weight:700}'
        '.v6-attempt{border-color:#61718c}.v6-denied{border-color:#b83232;background:#fff2f2}'
        '.v6-accepted{border-color:#287d42;background:#effaf1}'
        '.v6-delivered{border-color:#3175b5;background:#edf5ff}'
        '.v6-observed{border-color:#6843ad;background:#f4efff}'
        '.v6-report{border-color:#b57719;background:#fff6e9}'
        '.v6-evidence{border-color:#267e75}.v6-decision{border-color:#8b541e}'
        '</style>'
        '<section><h2>Agent response and stop status</h2><p>'
        + html.escape(str(record.get("status", "SOFTWARE_FIXTURE"))) + '</p><ul>'
        + capacity + '</ul><p>Exact initial role prompts and serialized observed inputs '
        'appear in each agent lane above. Final text is visible only if recorded; '
        'private internal reasoning is unavailable.</p></section>'
        '<section><h2>Frozen independent auditor status</h2><ul>'
        + "".join(rule_status) + '</ul><p>NO_ALERT is a decision on a candidate; '
        'NOT_EVALUATED means no candidate frame. ABSTAIN means the selected projection '
        'lacked required fields. None is a semantic policy label.</p></section>'
        '<section><h2>V6 collective event timeline</h2><p>Rows show actual recorded '
        'events in sequence. ATTEMPT, DENIED, ACCEPTED, DELIVERED and OBSERVED '
        'are different states; accepted writes do not prove recipient observation. '
        'Message content still requires blind human coding.</p>'
        + "".join(event_rows) + '</section>'
        '<section><h2>Agent self-reports — separate from independent auditor</h2>'
        + report_body + '</section>'
    )
    return base_html.replace("</body>", addition + "</body>")
