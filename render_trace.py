"""Read-only researcher replay of a saved v1 scripted fixture.

This is a privileged researcher artifact. It must never be used as an agent or
auditor input because it reads trusted/ground_truth.json and condition.json.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from events import EventLog
from protocol_v3 import ANSWER_KEYS, ARTIFACTS, A_PRIVATE_MEMO, MEMO_MARKER
from trace_v2 import TraceV2


FIXTURE_BANNER = "SCRIPTED FIXTURE — SOFTWARE ONLY, NOT LLM BEHAVIOR"


def load_fixture(root: Path) -> dict[str, Any]:
    events = [event.as_dict() for event in EventLog.read_jsonl(root / "trusted" / "events.jsonl").events]
    truth = json.loads((root / "trusted" / "ground_truth.json").read_text(encoding="utf-8"))
    condition = json.loads((root / "trusted" / "condition.json").read_text(encoding="utf-8"))
    score = json.loads((root / "score.json").read_text(encoding="utf-8"))
    return {"events": events, "truth": truth, "condition": condition, "score": score}


def _event_line(event: dict[str, Any], *, truth: dict[str, Any] | None = None) -> str:
    data = event["data"]
    detail = ", ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in sorted(data.items()))
    line = f"{event['seq']:03d} | {event['actor']} | {event['kind']} | {detail}"
    if truth is not None and event["kind"] == "observed":
        message = truth.get("messages", {}).get(data.get("message_id"), {})
        if "body" in message:
            line += f" | fixture content seen={json.dumps(message['body'], ensure_ascii=False)}"
    return line


def _agent_events(events: list[dict[str, Any]], actor: str) -> list[dict[str, Any]]:
    return [event for event in events if event["actor"] == actor or event["data"].get("recipient") == actor]


def build_text(fixture: dict[str, Any]) -> str:
    events, truth = fixture["events"], fixture["truth"]
    lines = [FIXTURE_BANNER, "Researcher-only replay; never export this artifact to an agent or auditor.",
             "LLM turns: NOT MEASURED", "Independent auditor: NOT EVALUATED", ""]
    for actor in "ABCD":
        lines += [f"=== Agent {actor}: recorded fixture actions and received reads ==="]
        lines += [_event_line(event, truth=truth) for event in _agent_events(events, actor)] or ["No recorded events"]
        lines.append("")
    lines += ["=== Global chronological event stream ==="]
    lines += [_event_line(event) for event in events]
    lines += ["", "=== Gate and reviewer decisions ==="]
    decisions = [event for event in events if event["kind"] in {
        "send_denied", "send_accepted", "channel_reported", "completion_approved"
    }]
    lines += [_event_line(event) for event in decisions] or ["No recorded decisions"]
    lines += ["", "=== Auditor ===", "NOT EVALUATED: no independent monitor verdict was recorded.", ""]
    lines += ["=== RESEARCHER-ONLY TRUTH — NEVER SEEN BY AGENTS OR AUDITOR ===",
              "Fixture annotations and treatment are synthetic test data, not findings.",
              json.dumps({"condition": fixture["condition"], "ground_truth": truth,
                          "score": fixture["score"]}, indent=2, sort_keys=True, ensure_ascii=False)]
    return "\n".join(lines) + "\n"


def build_html(fixture: dict[str, Any]) -> str:
    """Generate a static privileged HTML file. No JavaScript, network, or model calls."""
    events, truth = fixture["events"], fixture["truth"]

    def pre(text: str) -> str:
        return "<pre>" + html.escape(text) + "</pre>"

    agent_sections = []
    for actor in "ABCD":
        content = "\n".join(_event_line(e, truth=truth) for e in _agent_events(events, actor))
        agent_sections.append(f"<section><h2>Agent {actor}</h2>{pre(content or 'No recorded events')}</section>")
    decisions = [e for e in events if e["kind"] in {
        "send_denied", "send_accepted", "channel_reported", "completion_approved"
    }]
    global_lines = "\n".join(_event_line(e) for e in events)
    decision_lines = "\n".join(_event_line(e) for e in decisions)
    truth_text = json.dumps({"condition": fixture["condition"], "ground_truth": truth,
                             "score": fixture["score"]}, indent=2, sort_keys=True, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Collective Blind Spot — scripted replay</title>
<style>body{{font:15px system-ui,sans-serif;margin:2rem;max-width:1400px;background:#f7f8fa;color:#17202a}}
.banner{{background:#732624;color:#fff;padding:1rem;font-weight:700}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
section{{background:#fff;border:1px solid #ccd3dc;padding:1rem;margin:1rem 0}} pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px ui-monospace,monospace}}
.truth{{border:3px solid #732624}} @media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style></head>
<body><h1>Collective Blind Spot — researcher replay</h1><p class="banner">{FIXTURE_BANNER}</p>
<p>Researcher-only artifact. Never use this page as an agent or auditor input. LLM turns: <strong>NOT MEASURED</strong>. Independent auditor: <strong>NOT EVALUATED</strong>.</p>
<div class="grid">{''.join(agent_sections)}</div>
<section><h2>Global chronological event stream</h2>{pre(global_lines)}</section>
<section><h2>Gate, report, and reviewer decisions</h2>{pre(decision_lines or 'No recorded decisions')}</section>
<section><h2>Auditor</h2><p>NOT EVALUATED: no independent monitor verdict was recorded.</p></section>
<section class="truth"><h2>RESEARCHER-ONLY TRUTH — NEVER SEEN BY AGENTS OR AUDITOR</h2>
<p>Fixture annotations and treatment are synthetic test data, not findings.</p>{pre(truth_text)}</section>
</body></html>\n"""


def load_model_run(root: Path) -> dict[str, Any]:
    """Load a researcher-only v3 mock/real run; never use as an auditor export."""
    trusted = root / "trusted"
    manifest = json.loads((trusted / "manifest.json").read_text(encoding="utf-8"))
    if manifest["provenance"] not in {"MOCK MODEL", "REAL MODEL"}:
        raise ValueError("Unknown run provenance")
    trace = TraceV2.read_jsonl(trusted / "events_v2.jsonl")
    verdict_path = root / "auditor" / "verdicts.jsonl"
    verdicts = ([json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines()
                 if line.strip()] if verdict_path.exists() else [])
    projection_path = root / "auditor" / "pooled_metadata.jsonl"
    auditor_frames = ([json.loads(line) for line in projection_path.read_text(encoding="utf-8").splitlines()
                       if line.strip()] if projection_path.exists() else [])
    def read(name: str) -> Any:
        return json.loads((trusted / name).read_text(encoding="utf-8"))
    inputs = {f"model_inputs/{p.name}": p.read_text(encoding="utf-8")
              for p in sorted((trusted / "model_inputs").glob("*.json"))}
    outputs = {f"model_outputs/{p.name}": p.read_text(encoding="utf-8")
               for p in sorted((trusted / "model_outputs").glob("*.json"))}
    progress_path = root.parent / "progress.jsonl"
    timestamps = {}
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("cell") == root.name and item.get("kind") == "event":
                timestamps[item["event_id"]] = item["utc"]
    return {"provenance": manifest["provenance"], "manifest": manifest,
            "events": [e.as_dict() for e in trace.events], "verdicts": verdicts,
            "auditor_frames": auditor_frames,
            "timestamps": timestamps,
            "inputs": inputs, "outputs": outputs, "tool_calls": read("tool_calls.json"),
            "messages": read("messages.json"), "evidence": read("evidence.json"),
            "outcome": read("outcome.json"), "review_queue": read("human_review_queue.json"),
            "researcher_only_setup": {"artifacts": ARTIFACTS, "answer_keys": ANSWER_KEYS,
                                      "private_memo": A_PRIVATE_MEMO, "marker": MEMO_MARKER}}


def build_model_text(run: dict[str, Any]) -> str:
    banner = f"{run['provenance']} — {'CANNED SOFTWARE INPUT, NOT BEHAVIORAL EVIDENCE' if run['provenance'] == 'MOCK MODEL' else 'CAPTURED MODEL RUN'}"
    lines = [banner, "RESEARCHER ONLY — contains private model inputs and trusted truth.",
             "Private internal reasoning: NOT AVAILABLE. Visible responses and tool calls only.",
             f"Run: {run['manifest']['run_id']}", ""]
    for actor in "ABCD":
        lines.append(f"=== Agent {actor}: captured inputs, outputs, and tools ===")
        for event in run["events"]:
            if event["actor"] != actor:
                continue
            if event["kind"] == "model_input_captured":
                ref = event["data"]["input_ref"]
                lines.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} INPUT {ref} sha256={event['data']['input_sha256']}")
                lines.append(run["inputs"][ref])
            elif event["kind"] == "model_output_captured":
                ref = event["data"]["output_ref"]
                lines.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} OUTPUT {ref} sha256={event['data']['output_sha256']}")
                lines.append(run["outputs"][ref])
            elif event["kind"] in {"tool_invocation", "tool_result", "recipient_observation"}:
                lines.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} {event['kind']} {json.dumps(event['data'], sort_keys=True)}")
        for call in run["tool_calls"]:
            if call["actor"] == actor:
                lines.append(f"{call['call_id']} TOOL {call['tool_name']} args={json.dumps(call['arguments'], sort_keys=True)} result={json.dumps(call['result'], sort_keys=True)}")
        lines.append("")
    lines.append("=== Global chronological event stream ===")
    lines.extend(f"{e['event_id']} {run['timestamps'].get(e['event_id'], 'TIME_NOT_CAPTURED')} seq={e['seq']} {e['actor']} {e['kind']} {json.dumps(e['data'], sort_keys=True)}"
                 for e in run["events"])
    lines += ["", "=== Gate, reports, and T4 reviewer ==="]
    lines.extend(f"{e['event_id']} {e['kind']} {json.dumps(e['data'], sort_keys=True)}" for e in run["events"]
                 if e["kind"] in {"authorization_denial", "accepted_write", "agent_discovery_report", "supervisor_decision"})
    lines += ["", f"=== Independent monitor: R1/R2 on {len(run['auditor_frames'])} pooled metadata frames ==="]
    lines.extend(json.dumps(frame, sort_keys=True) for frame in run["auditor_frames"])
    lines += ["", "=== Independent monitor verdicts ==="]
    lines.extend(json.dumps(v, sort_keys=True) for v in run["verdicts"])
    if not run["verdicts"]:
        lines.append("No rule candidate triggered; no verdict was emitted. R1/R2 were evaluated at each pooled-frame cutoff.")
    lines += ["", "=== Verified task state ===", json.dumps(run["outcome"], sort_keys=True, indent=2),
              "", "=== RESEARCHER-ONLY TRUTH — NEVER AGENT/AUDITOR INPUT ===",
              json.dumps({"manifest": run["manifest"], "messages": run["messages"],
                          "evidence": run["evidence"], "human_review_queue": run["review_queue"],
                          "setup": run["researcher_only_setup"]},
                         sort_keys=True, indent=2, ensure_ascii=False)]
    return "\n".join(lines) + "\n"


def build_model_html(run: dict[str, Any]) -> str:
    def panel(title: str, body: str, *, cls: str = "") -> str:
        return f'<section class="{cls}"><h2>{html.escape(title)}</h2><pre>{html.escape(body)}</pre></section>'
    pieces = []
    for actor in "ABCD":
        entries = []
        for event in run["events"]:
            if event["actor"] != actor:
                continue
            if event["kind"] == "model_input_captured":
                ref = event["data"]["input_ref"]
                entries.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} INPUT {ref} sha256={event['data']['input_sha256']}\n{run['inputs'][ref]}")
            elif event["kind"] == "model_output_captured":
                ref = event["data"]["output_ref"]
                entries.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} OUTPUT {ref} sha256={event['data']['output_sha256']}\n{run['outputs'][ref]}")
            elif event["kind"] == "recipient_observation":
                entries.append(f"{event['event_id']} {run['timestamps'].get(event['event_id'], 'TIME_NOT_CAPTURED')} OBSERVED {json.dumps(event['data'], sort_keys=True)}")
        entries.extend(f"{call['call_id']} TOOL {call['tool_name']} args={json.dumps(call['arguments'], sort_keys=True)} result={json.dumps(call['result'], sort_keys=True)}"
                       for call in run["tool_calls"] if call["actor"] == actor)
        pieces.append(panel(f"Agent {actor}: exact captured inputs/outputs and tools", "\n\n".join(entries)))
    global_text = "\n".join(f"{e['event_id']} {run['timestamps'].get(e['event_id'], 'TIME_NOT_CAPTURED')} seq={e['seq']} {e['actor']} {e['kind']} {json.dumps(e['data'], sort_keys=True)}"
                            for e in run["events"])
    gate_text = "\n".join(f"{e['event_id']} {e['kind']} {json.dumps(e['data'], sort_keys=True)}"
                          for e in run["events"] if e["kind"] in {
                              "authorization_denial", "accepted_write", "agent_discovery_report", "supervisor_decision"})
    verdict_text = "\n".join(json.dumps(v, sort_keys=True) for v in run["verdicts"]) or "No rule candidate triggered; no verdict was emitted. R1/R2 were evaluated at each pooled-frame cutoff."
    frame_text = "\n".join(json.dumps(frame, sort_keys=True) for frame in run["auditor_frames"])
    truth_text = json.dumps({"manifest": run["manifest"], "messages": run["messages"],
                             "evidence": run["evidence"], "human_review_queue": run["review_queue"],
                             "setup": run["researcher_only_setup"]},
                            indent=2, sort_keys=True, ensure_ascii=False)
    banner = ("MOCK MODEL — CANNED SOFTWARE INPUT, NOT BEHAVIORAL EVIDENCE"
              if run["provenance"] == "MOCK MODEL" else "REAL MODEL — CAPTURED RUN")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Collective Blind Spot replay</title>
<style>body{{font:15px system-ui;margin:2rem;background:#f7f8fa;color:#17202a}}section{{border:1px solid #ccd3dc;background:#fff;padding:1rem;margin:1rem 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px ui-monospace,monospace}}.banner{{background:#732624;color:#fff;padding:1rem;font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}.truth{{border:3px solid #732624}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}</style></head>
<body><h1>Collective Blind Spot — researcher replay</h1><p class="banner">{banner}</p>
<p>RESEARCHER ONLY. Private inputs and trusted truth appear here. Never use this page as agent or auditor input. Private internal reasoning: NOT AVAILABLE.</p>
<div class="grid">{''.join(pieces)}</div>
{panel('Global chronological event stream', global_text)}
{panel('Gate, reports, and T4 reviewer', gate_text)}
{panel('Independent monitor input: exact pooled metadata frames', frame_text)}
{panel('Independent monitor verdicts', verdict_text)}
{panel('Verified task state', json.dumps(run['outcome'], indent=2, sort_keys=True))}
{panel('RESEARCHER-ONLY TRUTH — NEVER AGENT/AUDITOR INPUT', truth_text, cls='truth')}
</body></html>\n"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a saved scripted fixture for researcher inspection")
    parser.add_argument("fixture_dir", type=Path, help="Directory containing trusted/, auditor/, and score.json")
    parser.add_argument("--text", type=Path, help="Optional researcher-only text output")
    parser.add_argument("--html", type=Path, help="Optional researcher-only static HTML output")
    args = parser.parse_args()
    is_model_run = (args.fixture_dir / "trusted" / "events_v2.jsonl").exists()
    loaded = load_model_run(args.fixture_dir) if is_model_run else load_fixture(args.fixture_dir)
    content = build_model_text(loaded) if is_model_run else build_text(loaded)
    if args.text:
        args.text.parent.mkdir(parents=True, exist_ok=True)
        args.text.write_text(content, encoding="utf-8")
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(build_model_html(loaded) if is_model_run else build_html(loaded), encoding="utf-8")
    if not args.text and not args.html:
        print(content, end="")


if __name__ == "__main__":
    main()
