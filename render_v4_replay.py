"""Researcher-only v4 replay additions. Never used as agent or auditor input."""

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
    for event in run["events"]:
        kind = event["kind"]
        category = STATUS_CLASSES.get(kind, "other")
        data = event["data"]
        event_id = html.escape(event["event_id"])
        stamp = html.escape(run["timestamps"].get(event["event_id"], "TIME_NOT_CAPTURED"))
        actor = html.escape(event["actor"])
        detail = html.escape(json.dumps(data, sort_keys=True, ensure_ascii=False))
        row = (f'<div class="v4-event v4-{category}"><span class="v4-badge">'
               f'{html.escape(kind)}</span> <b>{event_id}</b> '
               f'<time>{stamp}</time> seq={event["seq"]} actor={actor}'
               f'<pre>{detail}</pre></div>')
        if kind == "agent_discovery_report":
            reports.append(row)
        else:
            event_rows.append(row)
    report_body = "".join(reports) or "<p>No agent discovery report was recorded.</p>"
    addition = (
        '<style>.v4-event{border-left:6px solid #8995a5;padding:.5rem 1rem;'
        'margin:.35rem 0;background:#f8fafc}.v4-event pre{margin:.3rem 0}.v4-badge{'
        'display:inline-block;background:#e4eaf0;padding:.15rem .4rem;font-weight:700}'
        '.v4-attempt{border-color:#61718c}.v4-denied{border-color:#b83232;background:#fff2f2}'
        '.v4-accepted{border-color:#287d42;background:#effaf1}'
        '.v4-delivered{border-color:#3175b5;background:#edf5ff}'
        '.v4-observed{border-color:#6843ad;background:#f4efff}'
        '.v4-report{border-color:#b57719;background:#fff6e9}'
        '.v4-evidence{border-color:#267e75}.v4-decision{border-color:#8b541e}'
        '</style>'
        '<section><h2>V4 collective event timeline</h2><p>Rows show actual recorded '
        'events in sequence. ATTEMPT, DENIED, ACCEPTED, DELIVERED and OBSERVED '
        'are different states; accepted writes do not prove recipient observation. '
        'Message content still requires blind human coding.</p>'
        + "".join(event_rows) + '</section>'
        '<section><h2>Agent self-reports — separate from independent auditor</h2>'
        + report_body + '</section>'
    )
    return base_html.replace("</body>", addition + "</body>")
