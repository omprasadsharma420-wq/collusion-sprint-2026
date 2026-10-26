"""Researcher-only side-by-side rendering of constructed control traces."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .audit_controls import export


def render(root: Path) -> None:
    result = export(root)
    cases = result["cases"]
    columns = []
    for case in cases:
        title = case["case_id"]
        frame_lines = "\n".join(
            f'{f["event_id"]} {f["kind"]} actor={f["actor"]} data={json.dumps(f["data"], sort_keys=True)}'
            for f in case["frames"])
        verdict_lines = "\n".join(
            f'{v["rule_id"]}: {v["verdict"]} at seq {v["decision_seq"]}; '
            f'evidence={v["evidence_event_ids"]}; reason={v["reason"]}'
            for v in case["verdicts"]) or "R1/R2: NOT EVALUATED (no candidate action)"
        columns.append((title, frame_lines, verdict_lines, case["private_truth"]))
    lines = ["SCRIPTED SOFTWARE CONTROL — researcher comparison; no model was run.",
             f'Paired allowlisted monitor-input bytes identical: {result["paired_bytes_identical"]}',
             f'Paired R1/R2 verdicts identical: {result["paired_verdicts_identical"]}',
             "Trusted payload digests differ; payload digests are excluded from this allowlisted view.",
             "R2 is NOT EVALUATED when no approve_release candidate exists.", ""]
    for title, frames, verdicts, truth in columns:
        lines.extend([f"=== {title} ===", "AUDITOR INPUT — ALLOWLISTED POOLED METADATA", frames,
                      "FROZEN R1/R2 VERDICTS", verdicts, "RESEARCHER ONLY — PRIVILEGED TRUTH",
                      json.dumps(truth, indent=2, ensure_ascii=False), ""])
    (root / "RESEARCHER_COMPARISON.txt").write_text("\n".join(lines), encoding="utf-8")
    cards = []
    for title, frames, verdicts, truth in columns:
        cards.append(
            "<section><h2>" + html.escape(title) + "</h2>"
            "<h3>Auditor input: allowlisted pooled metadata</h3><pre>" + html.escape(frames) + "</pre>"
            "<h3>Frozen R1/R2 verdicts</h3><pre>" + html.escape(verdicts) + "</pre>"
            "<div class='truth'><h3>RESEARCHER ONLY — privileged truth</h3><pre>"
            + html.escape(json.dumps(truth, indent=2, ensure_ascii=False)) + "</pre></div></section>")
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><title>V7 scripted auditor controls</title>
<style>body{font:16px system-ui;margin:2rem;background:#f8f8f4;color:#18251f}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}section{background:white;padding:1rem;border:1px solid #aaa;min-width:0}pre{font:12px ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.truth{background:#fff0dc;border:2px solid #9b5000;padding:.5rem}h1{font-size:1.5rem}@media(max-width:1000px){main{grid-template-columns:1fr}}</style>
<h1>SCRIPTED SOFTWARE CONTROL — researcher-only comparison</h1>"""
    page += (f'<p>Paired auditor-input bytes identical: <strong>{result["paired_bytes_identical"]}</strong>. '
             f'Frozen R1/R2 verdicts identical: <strong>{result["paired_verdicts_identical"]}</strong>. '
             'Trusted payload digests differ and are excluded from this allowlisted view. '
             'R2 is <strong>NOT EVALUATED</strong> without an approval candidate. '
             'These constructed controls are not observed model behavior.</p><main>'
             + "".join(cards) + "</main></html>")
    (root / "RESEARCHER_COMPARISON.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.output)
    print((args.output / "RESEARCHER_COMPARISON.txt").read_text(encoding="utf-8"))
