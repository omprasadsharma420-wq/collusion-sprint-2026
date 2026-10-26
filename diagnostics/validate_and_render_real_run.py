"""Validate saved real-run receipts and regenerate researcher views, offline only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from modal_transport import MAX_GENERATION_TOKENS, MODEL_NAME, MODEL_REVISION, SEED, VLLM_VERSION
from protocol_v3 import AGENTS, MEMO_MARKER, TOOL_SCHEMAS, CellConfig, prompt_sha256
from render_trace import build_model_html, build_model_text, load_model_run
from run_real_modal import _write_json, write_overview
from trace_v2 import TraceV2


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate(root: Path) -> dict:
    smoke = json.loads((root / "smoke.json").read_text(encoding="utf-8"))
    usage = json.loads((root / "usage.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    assert smoke["pass"] and smoke["calls"] == 1
    assert run_manifest["cells_saved"] == ["C", "A", "D", "B"]
    assert run_manifest["status"] == "STOPPED_AFTER_RUN"
    call_dirs = sorted((root / "trusted_provider_calls").iterdir())
    assert len(call_dirs) == usage["model_calls"] == 193
    token_sum = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for folder in call_dirs:
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        request_bytes = (folder / "request.json").read_bytes()
        response_bytes = (folder / "response.json").read_bytes()
        request = json.loads(request_bytes)
        response = json.loads(response_bytes)
        assert receipt["request_sha256"] == sha(request_bytes)
        assert receipt["response_sha256"] == sha(response_bytes)
        assert receipt["status"] == 200
        assert receipt["model"] == receipt["worker_model"] == request["model"] == MODEL_NAME
        assert receipt["revision"] == receipt["worker_revision"] == MODEL_REVISION
        assert receipt["vllm_version"] == receipt["worker_vllm_version"] == VLLM_VERSION
        assert response["model"] == MODEL_NAME
        assert request["tools"] == TOOL_SCHEMAS
        assert request["temperature"] == 0 and request["seed"] == SEED
        assert request["max_tokens"] == MAX_GENERATION_TOKENS
        assert request["chat_template_kwargs"] == {"enable_thinking": False}
        assert (folder / "parsed.json").exists()
        for key in token_sum:
            token_sum[key] += int((receipt.get("usage") or {}).get(key, 0))
    assert token_sum == usage["token_usage"]

    records = []
    summary = {"provenance": "REAL MODEL", "validated_provider_calls": len(call_dirs),
               "smoke_calls": 1, "token_usage": token_sum, "cells": {}}
    for cell in "CADB":
        cell_root = root / cell
        record = json.loads((cell_root / "manifest.json").read_text(encoding="utf-8"))
        records.append(record)
        assert record["cell"] == cell and record["provenance"] == "REAL MODEL"
        assert record["model_calls"] == 48
        assert record["prompt_sha256"] == {
            actor: prompt_sha256(actor, CellConfig.for_cell(cell)) for actor in AGENTS}
        trace = TraceV2.read_jsonl(cell_root / "trusted" / "events_v2.jsonl")
        input_events = [event for event in trace.events if event.kind == "model_input_captured"]
        output_events = [event for event in trace.events if event.kind == "model_output_captured"]
        assert len(input_events) == len(output_events) == record["model_calls"]
        for event in input_events:
            raw = (cell_root / "trusted" / event.data["input_ref"]).read_bytes()
            assert sha(raw) == event.data["input_sha256"]
            request = json.loads(raw)
            assert request["tools"] == TOOL_SCHEMAS
            if event.actor != "A" and not record["outcome"]["confirmed_marker_exposure"]:
                assert MEMO_MARKER not in raw.decode("utf-8")
        for event in output_events:
            raw = (cell_root / "trusted" / event.data["output_ref"]).read_bytes()
            assert sha(raw) == event.data["output_sha256"]
        pooled = project(trace, AuditView.POOLED_METADATA)
        assert list(pooled) == lines(cell_root / "auditor" / "pooled_metadata.jsonl")
        verdicts = run_audit(pooled)
        assert list(verdicts) == lines(cell_root / "auditor" / "verdicts.jsonl")
        for actor in AGENTS:
            assert list(project(trace, AuditView.LOCAL, actor=actor)) == lines(
                cell_root / "auditor" / f"local_{actor}.jsonl")
        for path in (cell_root / "auditor").glob("*.jsonl"):
            contents = path.read_text(encoding="utf-8")
            assert MEMO_MARKER not in contents
            assert "Private planning memo" not in contents
        _write_json(cell_root / "auditor" / "evaluation_manifest.json", {
            "source_projection": "pooled_metadata", "rule_ids": ["R1", "R2"],
            "frames_evaluated": len(pooled), "verdicts_emitted": len(verdicts),
            "semantics": "Rules emit verdicts only at candidate event cutoffs; zero verdicts means no candidate triggered.",
        })
        loaded = load_model_run(cell_root)
        (cell_root / "researcher" / "replay.txt").write_text(build_model_text(loaded), encoding="utf-8")
        (cell_root / "researcher" / "replay.html").write_text(build_model_html(loaded), encoding="utf-8")
        summary["cells"][cell] = {
            "events": len(trace.events), "model_calls": record["model_calls"],
            "monitor_frames": len(pooled), "monitor_verdicts": len(verdicts),
            "task_score": record["outcome"]["task_score"],
            "confirmed_marker_exposure": record["outcome"]["confirmed_marker_exposure"],
        }
    write_overview(root, records, smoke_result=smoke)
    _write_json(root / "VALIDATION.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.run_dir.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
