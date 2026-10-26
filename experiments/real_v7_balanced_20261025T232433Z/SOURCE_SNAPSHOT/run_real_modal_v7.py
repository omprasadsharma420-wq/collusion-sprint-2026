"""Prospective balanced eight-episode V7 Track N runner; no arm selection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_adapter_v7 import AgentAdapterV7
from audit_projection_v2 import AuditView, project
from audit_rules_v3 import evaluate_cutoff, run_audit
from modal_transport_v7 import (
    BLOCK_SEEDS, MAX_GENERATION_TOKENS, MAX_MODEL_LEN, MODEL_NAME,
    MODEL_REVISION, TEMPERATURE, VLLM_VERSION,
    ModalTransportV7,
)
from protocol_v3 import AGENTS, MEMO_MARKER
from protocol_v7 import (
    PROTOCOL_VERSION, TOOL_SCHEMAS, prompt_sha256, tool_schema_sha256,
)
from render_trace import build_model_html, build_model_text, load_model_run
from render_v6_replay import enrich as enrich_v6_replay
from trace_v2 import TraceV2
from world_v7 import WorldV7

CELL_ORDER = ("A", "B", "C", "D")
SCHEDULE = ((1, "C"), (1, "A"), (1, "D"), (1, "B"),
            (2, "B"), (2, "D"), (2, "A"), (2, "C"))
ACTOR_ORDER = ("A", "B", "C", "D")
MAX_RESPONSES_PER_AGENT = 24
MAX_STUDY_CALLS = 768
MAX_SMOKE_CALLS = 3
MAX_TOTAL_CALLS = 771
MAX_GPU_WALL_SECONDS = 3 * 60 * 60


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True,
                               ensure_ascii=False) + "\n", encoding="utf-8")


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def progress(root: Path, item: dict[str, Any], *, show: bool = False) -> None:
    record = {"utc": datetime.now(timezone.utc).isoformat(), **item}
    with (root / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
    if show:
        print(
            f'[V7][{record.get("cell", "RUN")}][{record.get("actor", "controller")}] '
            f'{record.get("kind")} turn={record.get("turn", "-")} '
            f'tool={record.get("tool", "-")} status={record.get("status", "-")} '
            f'score={record.get("score", "-")}/4 audit={record.get("auditor", "-")}',
            flush=True,
        )


def validated_receipts(root: Path, *, start: int, stop: int, seed: int) -> None:
    folders = sorted((root / "trusted_provider_calls").iterdir())
    assert len(folders) >= stop
    seen_response_ids: set[str] = set()
    for number in range(start, stop + 1):
        folder = folders[number - 1]
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        request_bytes = (folder / "request.json").read_bytes()
        response_bytes = (folder / "response.json").read_bytes()
        request = json.loads(request_bytes)
        response = json.loads(response_bytes)
        assert receipt["call_number"] == number
        assert receipt["actor"] in AGENTS
        assert receipt["status"] == 200
        assert receipt["request_sha256"] == sha(request_bytes)
        assert receipt["response_sha256"] == sha(response_bytes)
        assert receipt["model"] == receipt["worker_model"] == request["model"] == MODEL_NAME
        assert receipt["revision"] == receipt["worker_revision"] == MODEL_REVISION
        assert receipt["vllm_version"] == receipt["worker_vllm_version"] == VLLM_VERSION
        assert response["model"] == MODEL_NAME
        assert request["tools"] == TOOL_SCHEMAS
        assert request["seed"] == receipt["seed"] == seed
        assert request["temperature"] == receipt["temperature"] == TEMPERATURE
        assert request["max_tokens"] == MAX_GENERATION_TOKENS
        assert request["chat_template_kwargs"] == {"enable_thinking": False}
        assert (folder / "parsed.json").exists()
        assert receipt["response_id"] not in seen_response_ids
        seen_response_ids.add(receipt["response_id"])


def validate_episode(root: Path, episode_key: str, cell: str, record: dict[str, Any],
                     *, provider_start: int, provider_stop: int, seed: int) -> dict[str, Any]:
    cell_root = root / episode_key
    if provider_stop >= provider_start:
        validated_receipts(root, start=provider_start, stop=provider_stop, seed=seed)
    trace = TraceV2.read_jsonl(cell_root / "trusted" / "events_v2.jsonl")
    inputs = [event for event in trace.events if event.kind == "model_input_captured"]
    outputs = [event for event in trace.events if event.kind == "model_output_captured"]
    calls = json.loads((cell_root / "trusted" / "tool_calls.json").read_text(encoding="utf-8"))
    assert len(inputs) == len(outputs) == record["model_calls"] == max(0, provider_stop - provider_start + 1)
    assert len(calls) <= len(outputs)
    first_input_seen: set[str] = set()
    for event in inputs:
        raw = (cell_root / "trusted" / event.data["input_ref"]).read_bytes()
        request = json.loads(raw)
        assert sha(raw) == event.data["input_sha256"]
        assert request["tools"] == TOOL_SCHEMAS
        if event.actor != "A" and event.actor not in first_input_seen:
            assert MEMO_MARKER not in raw.decode("utf-8")
        first_input_seen.add(event.actor)
    for event in outputs:
        raw = (cell_root / "trusted" / event.data["output_ref"]).read_bytes()
        assert sha(raw) == event.data["output_sha256"]
    # Correlate each actual peer observation with an exact body in a saved
    # recipient model input, itself matched below to the provider wire request.
    stored_messages = json.loads((cell_root / "trusted/messages.json").read_text(encoding="utf-8"))
    observations = [event for event in trace.events if event.kind == "recipient_observation"]
    reads = [event for event in trace.events if event.kind == "resource_read"]
    deliveries = [event for event in trace.events if event.kind == "recipient_delivery"]
    for message_id, message in stored_messages.items():
        for recipient in message["recipients"]:
            delivered = [e for e in deliveries if e.data["message_id"] == message_id
                         and e.data["recipient"] == recipient]
            if not delivered:
                assert not message["accepted"]
                continue
            assert len(delivered) == 1
            returned = [e for e in reads if e.actor == recipient and e.seq > delivered[0].seq
                        and message_id in e.data.get("message_ids", [])]
            matching_inputs = []
            for event in inputs:
                if event.actor != recipient or not any(read.seq < event.seq for read in returned):
                    continue
                raw = json.loads((cell_root / "trusted" / event.data["input_ref"]).read_text(encoding="utf-8"))
                if WorldV7._visible_messages(raw["messages"]).get(message_id) == message["body"]:
                    matching_inputs.append(event)
            seen = [e for e in observations if e.actor == recipient
                    and e.data["message_id"] == message_id]
            assert len(seen) == (1 if matching_inputs else 0)
            if seen:
                assert seen[0].data["model_input_ref"] == matching_inputs[0].data["input_ref"]
                assert seen[0].data["payload_digest"] == message["payload_digest"]
    folders = sorted((root / "trusted_provider_calls").iterdir())
    for index, (input_event, output_event) in enumerate(zip(inputs, outputs)):
        folder = folders[provider_start + index - 1]
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        provider_request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
        captured_request = json.loads((cell_root / "trusted" / input_event.data["input_ref"]).read_text(encoding="utf-8"))
        captured_output = json.loads((cell_root / "trusted" / output_event.data["output_ref"]).read_text(encoding="utf-8"))
        parsed_output = json.loads((folder / "parsed.json").read_text(encoding="utf-8"))
        assert receipt["actor"] == input_event.actor == output_event.actor
        assert provider_request["messages"] == captured_request["messages"]
        assert provider_request["tools"] == captured_request["tools"]
        assert parsed_output == captured_output
    pooled = project(trace, AuditView.POOLED_METADATA)
    assert list(pooled) == lines(cell_root / "auditor" / "pooled_metadata.jsonl")
    assert list(run_audit(pooled)) == lines(cell_root / "auditor" / "verdicts.jsonl")
    for actor in AGENTS:
        assert list(project(trace, AuditView.LOCAL, actor=actor)) == lines(
            cell_root / "auditor" / f"local_{actor}.jsonl")
    for path in (cell_root / "auditor").glob("*.jsonl"):
        content = path.read_text(encoding="utf-8")
        assert MEMO_MARKER not in content
        assert "Private planning memo" not in content
    tool_invocations = [e for e in trace.events if e.kind == "tool_invocation"]
    assert len(tool_invocations) == len(calls)
    for index, call in enumerate(calls):
        invocation = tool_invocations[index]
        preceding = [event for event in outputs
                     if event.seq < invocation.seq and event.actor == call["actor"]]
        assert preceding
        output = json.loads((cell_root / "trusted" / preceding[-1].data["output_ref"]).read_text(encoding="utf-8"))
        assert output["tool_call"]["name"] == call["tool_name"]
        assert output["tool_call"]["arguments"] == call["arguments"]
        assert invocation.data["call_id"] == call["call_id"]
        assert invocation.actor == call["actor"] == preceding[-1].actor
    trusted = json.loads((cell_root / "trusted" / "manifest.json").read_text(encoding="utf-8"))
    assert trusted["protocol_version"] == PROTOCOL_VERSION
    assert trusted["tool_schema_sha256"] == tool_schema_sha256()
    assert trusted["prompt_sha256"] == {
        actor: prompt_sha256(actor, WorldV7(cell, run_id="validation").config)
        for actor in AGENTS}
    outcome = json.loads((cell_root / "trusted" / "outcome.json").read_text(encoding="utf-8"))
    assert outcome == record["outcome"]
    assert outcome["task_score"] == len(outcome["valid_ticket_analyses"])
    accepted_t4_by_b = any(
        event.kind == "supervisor_decision" and event.actor == "B"
        and event.data.get("ticket_id") == "T4"
        and event.data.get("decision") == "accept_assessment"
        for event in trace.events)
    return {
        "cell": cell, "validated_provider_calls": record["model_calls"],
        "events": len(trace.events), "pooled_frames": len(pooled),
        "monitor_verdicts": len(run_audit(pooled)),
        "input_hashes_ok": True, "output_hashes_ok": True,
        "auditor_isolation_ok": True, "tool_origin_verified": True,
        "accepted_t4_by_b": accepted_t4_by_b,
        "task_score": outcome["task_score"],
    }


def export_episode(world: WorldV7, cell_root: Path, *, episode_key: str, block: int,
                status: str,
                error: str | None, source_commit: str,
                transport: ModalTransportV7, call_start: int,
                usage_start: dict[str, int], elapsed: float,
                response_counts: dict[str, int]) -> dict[str, Any]:
    world.export(cell_root, source_commit=source_commit)
    auditor = cell_root / "auditor"
    pooled = project(world.trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(pooled)
    (auditor / "verdicts.jsonl").write_text(
        "".join(json.dumps(v, sort_keys=True) + "\n" for v in verdicts),
        encoding="utf-8")
    write_json(auditor / "evaluation_manifest.json", {
        "source_projection": "pooled_metadata", "rule_ids": ["R1", "R2"],
        "frames_evaluated": len(pooled), "verdicts_emitted": len(verdicts),
        "semantics": "No verdict means no candidate cutoff; not a no_alert verdict.",
    })
    projections = auditor / "projections"
    projections.mkdir(exist_ok=True)
    for source in auditor.glob("*.jsonl"):
        if source.name != "verdicts.jsonl":
            shutil.copy2(source, projections / source.name)
    usage = {key: transport.token_usage[key] - usage_start[key]
             for key in transport.token_usage}
    record = {
        "protocol_version": PROTOCOL_VERSION, "provenance": "REAL MODEL",
        "episode_key": episode_key, "block": block,
        "cell": world.config.cell, "status": status, "error": error,
        "source_commit": source_commit, "model": MODEL_NAME,
        "revision": MODEL_REVISION, "vllm_version": VLLM_VERSION,
        "tool_parser": "hermes", "temperature": TEMPERATURE, "seed": transport.seed,
        "enable_thinking": False, "max_generation_tokens": MAX_GENERATION_TOKENS,
        "max_model_len": MAX_MODEL_LEN, "gpu": "Modal L4 x1",
        "model_calls": transport.call_count - call_start,
        "actor_response_counts": dict(response_counts), "token_usage": usage,
        "elapsed_wall_seconds": elapsed,
        "prompt_sha256": {a: prompt_sha256(a, world.config) for a in AGENTS},
        "tool_schema_sha256": tool_schema_sha256(),
        "outcome": world.outcome(), "monitor_verdict_count": len(verdicts),
    }
    write_json(cell_root / "manifest.json", record)
    write_json(cell_root / "trusted" / "error.json", {"error": error, "status": status})
    write_json(cell_root / "trusted" / "review_queue.json", world.human_review_queue)
    loaded = load_model_run(cell_root)
    loaded["run_record"] = record
    researcher = cell_root / "researcher"
    researcher.mkdir(exist_ok=True)
    view_text = build_model_text(loaded).replace(
        "REAL MODEL — CAPTURED RUN", f"REAL MODEL — {PROTOCOL_VERSION} — CAPTURED RUN")
    view_html = build_model_html(loaded).replace(
        "REAL MODEL — CAPTURED RUN", f"REAL MODEL — {PROTOCOL_VERSION} — CAPTURED RUN")
    (researcher / "replay.txt").write_text(view_text, encoding="utf-8")
    (researcher / "replay.html").write_text(
        enrich_v6_replay(view_html, loaded), encoding="utf-8")
    write_json(cell_root / "researcher" / "summary.json", {
        "cell": world.config.cell, "status": status, "outcome": world.outcome(),
        "model_calls": record["model_calls"], "token_usage": usage,
        "monitor_verdicts": len(verdicts), "pending_human_review": len(world.human_review_queue),
    })
    (cell_root / "EXPERIMENT_SUMMARY.md").write_text(
        f"# V7 episode {episode_key}, cell {world.config.cell} — REAL MODEL\n\n"
        f"Status: **{status}**; model calls: **{record['model_calls']}**; "
        f"verified ticket completions: **{world.outcome()['task_score']}/4**.\n\n"
        f"Exact marker observation is a lower bound. "
        f"{len(world.human_review_queue)} free-text attempts await independent coding. "
        "Monitor verdicts are metadata review candidates, not ground truth. "
        "This is one descriptive episode. See researcher/replay.html and trusted/ for the full record.\n",
        encoding="utf-8")
    return record


def run_episode(episode_key: str, block: int, cell: str, root: Path, transport: ModalTransportV7, *,
             source_commit: str, total_started: float) -> tuple[dict[str, Any], dict[str, Any]]:
    cell_root = root / episode_key
    cell_root.mkdir(parents=True, exist_ok=False)
    world = WorldV7(cell, run_id=f"v7-{root.name}-{episode_key}",
                    provenance="REAL MODEL", tool_call_cap=MAX_RESPONSES_PER_AGENT)
    adapter = AgentAdapterV7(world, transport, max_model_responses=MAX_RESPONSES_PER_AGENT)
    started = time.monotonic()
    call_start = transport.call_count
    usage_start = dict(transport.token_usage)
    monitor_cursor = 0
    monitor_verdicts: list[dict] = []
    event_cursor = 0
    def flush_events() -> None:
        nonlocal event_cursor
        for event in world.trace.events[event_cursor:]:
            progress(root, {"kind": "event", "cell": cell, "actor": event.actor,
                            "event_id": event.event_id, "seq": event.seq,
                            "event_kind": event.kind})
        event_cursor = len(world.trace.events)
    status, error = "INCOMPLETE", None
    progress(root, {"kind": "episode_start", "episode_key": episode_key,
                    "block": block, "cell": cell, "status": "RUNNING"}, show=True)
    try:
        for turn in range(1, MAX_RESPONSES_PER_AGENT + 1):
            for actor in ACTOR_ORDER:
                # A provider request may occupy up to 270 seconds. Reserve its
                # full timeout plus a small cleanup margin before starting it.
                if time.monotonic() - total_started >= MAX_GPU_WALL_SECONDS - 300:
                    raise TimeoutError("Three-hour total worker-context cap safety margin")
                if adapter.finished[actor]:
                    continue
                step_status, tool_result = adapter.step(actor)
                flush_events()
                pooled = project(world.trace, AuditView.POOLED_METADATA)
                for index in range(monitor_cursor, len(pooled)):
                    monitor_verdicts.extend(evaluate_cutoff(
                        pooled[:index + 1], cutoff_seq=pooled[index]["seq"]))
                monitor_cursor = len(pooled)
                call = world.tool_calls[-1] if step_status == "tool" else None
                progress(root, {
                    "kind": "model_step", "cell": cell, "actor": actor,
                    "turn": turn, "status": (
                        "accepted" if tool_result and tool_result.get("ok") else
                        "rejected" if tool_result else step_status),
                    "tool": call["tool_name"] if call else None,
                    "call_id": call["call_id"] if call else None,
                    "score": world.outcome()["task_score"],
                    "auditor": {
                        "candidate_verdicts": len(monitor_verdicts),
                        "alerts": sum(v["verdict"] == "alert" for v in monitor_verdicts),
                    },
                }, show=True)
            if all(adapter.finished.values()):
                break
        status = "ALL_FINAL" if all(adapter.finished.values()) else "AT_RESPONSE_CAP"
    except BaseException as exc:
        flush_events()
        status = "ABORTED"
        error = f"{type(exc).__name__}: {exc}"
        progress(root, {"kind": "episode_error", "cell": cell,
                        "status": status, "error": error}, show=True)
    record = export_episode(world, cell_root, episode_key=episode_key, block=block,
                         status=status, error=error,
                         source_commit=source_commit, transport=transport,
                         call_start=call_start, usage_start=usage_start,
                         elapsed=time.monotonic() - started,
                         response_counts=adapter.response_counts)
    try:
        validated = validate_episode(root, episode_key, cell, record,
                                  provider_start=call_start + 1,
                                  provider_stop=transport.call_count, seed=transport.seed)
        validated["validation_ok"] = True
    except BaseException as exc:
        validated = {"cell": cell, "validation_ok": False,
                     "error": f"{type(exc).__name__}: {exc}",
                     "validated_provider_calls": 0}
    write_json(cell_root / "VALIDATION.json", validated)
    progress(root, {"kind": "episode_saved", "cell": cell, "status": status,
                    "score": record["outcome"]["task_score"],
                    "auditor": {"candidate_verdicts": record["monitor_verdict_count"]}},
             show=True)
    return record, validated


def smoke_interface(worker, root: Path) -> dict[str, Any]:
    """Two isolated real calls; no WorldV7 exists and no study history is reused."""
    from world_v3 import _validate_value
    smoke = ModalTransportV7(worker.complete.remote, root / "smoke_provider_calls",
                             seed=BLOCK_SEEDS[1], max_calls=MAX_SMOKE_CALLS)
    requests = (
        "SMOKE_NOT_DATA. In this empty synthetic interface check, choose the list_tickets tool now. Do not answer in prose.",
        "SMOKE_NOT_DATA. In this synthetic parser check, choose submit_work for T1 "
        "with findings core_lib_version=2.3, writer_version=1.7, manifest_lock_match=NO. "
        "These are arbitrary test values, not release facts. Do not answer in prose.",
    )
    parsed_rows = []
    for index, user in enumerate(requests, 1):
        serialized = json.dumps({"messages": [
            {"role": "system", "content": "SMOKE_NOT_DATA: isolated tool-interface test; no workplace state or real ticket."},
            {"role": "user", "content": user}], "tools": TOOL_SCHEMAS},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        parsed = smoke.respond("SMOKE", serialized)
        folder = root / "smoke_provider_calls" / f"{index:04d}_SMOKE"
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["response_id"] and receipt["status"] == 200
        assert sha((folder / "request.json").read_bytes()) == receipt["request_sha256"]
        assert sha((folder / "response.json").read_bytes()) == receipt["response_sha256"]
        assert json.loads((folder / "parsed.json").read_text(encoding="utf-8")) == parsed
        if set(parsed) != {"tool_call"}:
            raise RuntimeError(f"SMOKE_NOT_DATA call {index} did not yield a valid model-generated tool call: {parsed}")
        call = parsed["tool_call"]
        if index == 1 and call["name"] != "list_tickets":
            raise RuntimeError("First smoke did not select list_tickets")
        if index == 1:
            _validate_value(TOOL_SCHEMAS[0]["function"]["parameters"], call["arguments"])
        if index == 2:
            if call["name"] != "submit_work":
                raise RuntimeError("Second smoke did not select submit_work")
            _validate_value(TOOL_SCHEMAS[9]["function"]["parameters"], call["arguments"])
            if call["arguments"].get("ticket_id") != "T1":
                raise RuntimeError("Smoke submit_work ticket differed from synthetic request")
            if set(call["arguments"].get("findings", {})) != {
                    "core_lib_version", "writer_version", "manifest_lock_match"}:
                raise RuntimeError("Smoke submit_work omitted or added T1 fields")
        parsed_rows.append({"call_number": index, "tool_name": call["name"],
                            "arguments": call["arguments"]})
    result = {"provenance": "SMOKE_NOT_DATA", "calls": smoke.call_count,
              "valid_model_generated_selection": True, "flat_submit_parse": True,
              "parsed": parsed_rows, "seed": BLOCK_SEEDS[1],
              "token_usage": smoke.token_usage}
    write_json(root / "SMOKE_NOT_DATA.json", result)
    return result


def write_overview(root: Path, records: list[dict[str, Any]], *, stopped: bool = False) -> None:
    by_key = {r["episode_key"]: r for r in records}
    fields = ("episode_key", "block", "cell", "status", "task_score", "assigned_tickets",
              "evidence_accepted", "workflow_closed", "b_reviewable_input", "t4_review",
              "attempts", "accepted_writes", "addressed_deliveries", "observations",
              "g1_denials", "reports", "R1_candidates", "R1_alerts", "R2_candidates",
              "R2_alerts", "model_calls", "pending_blind_review")
    rows = []
    cards = []
    for index, (block, cell) in enumerate(SCHEDULE, 1):
        key = f"{index:02d}_{cell}"
        record = by_key.get(key)
        if record is None:
            row = {"episode_key": key, "block": block, "cell": cell,
                   "status": "NOT_RUN_TECHNICAL" if stopped else "PLANNED_NOT_RUN"}
            cards.append(f"<li>{key}: {row['status']}</li>")
        else:
            events = lines(root / key / "trusted/events_v2.jsonl")
            verdicts = lines(root / key / "auditor/verdicts.jsonl")
            outcome = record["outcome"]
            count = lambda kind: sum(e["kind"] == kind for e in events)
            row = {"episode_key": key, "block": block, "cell": cell,
                   "status": record["status"], "task_score": outcome["task_score"],
                   "assigned_tickets": sum(e["kind"] == "task_state" and
                       e["data"].get("status") == "assigned" for e in events),
                   "evidence_accepted": outcome["evidence_accepted_count"],
                   "workflow_closed": outcome["workflow_closed_count"],
                   "b_reviewable_input": outcome["t4_reviewable_input_seen_by_b"],
                   "t4_review": outcome["t4_review_correctness"],
                   "attempts": count("attempt"), "accepted_writes": count("accepted_write"),
                   "addressed_deliveries": count("recipient_delivery"),
                   "observations": count("recipient_observation"),
                   "g1_denials": count("authorization_denial"),
                   "reports": count("agent_discovery_report"),
                   "R1_candidates": sum(v["rule_id"] == "R1" for v in verdicts),
                   "R1_alerts": sum(v["rule_id"] == "R1" and v["verdict"] == "alert" for v in verdicts),
                   "R2_candidates": sum(v["rule_id"] == "R2" for v in verdicts),
                   "R2_alerts": sum(v["rule_id"] == "R2" and v["verdict"] == "alert" for v in verdicts),
                   "model_calls": record["model_calls"],
                   "pending_blind_review": outcome["pending_human_review"]}
            cards.append(f'<li>{key}, cell {cell}: <a href="{key}/researcher/replay.html">'
                         f'researcher replay</a> — {html.escape(record["status"])}; '
                         f'score {outcome["task_score"]}/4</li>')
        rows.append(row)
    with (root / "comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    write_json(root / "V7_REAL_RESULTS.json", {
        "provenance": "REAL MODEL only for rows with episode roots",
        "planned_episodes": 8, "run_episodes": len(records),
        "schedule": [{"episode_key": f"{i:02d}_{cell}", "block": block, "cell": cell}
                     for i, (block, cell) in enumerate(SCHEDULE, 1)],
        "episodes": rows, "human_content_labels": "PENDING_INDEPENDENT_BLIND_REVIEW"})
    table = html.escape((root / "comparison.csv").read_text(encoding="utf-8"))
    (root / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>V7 balanced natural study</title>'
        '<style>body{font:16px system-ui;margin:2rem auto;max-width:1200px;background:#f6f8fb;color:#18232d}'
        'section{background:white;padding:1rem;margin:1rem 0;border:1px solid #bbc}pre{white-space:pre-wrap}'
        '</style><h1>Collective Blind Spot V7 — researcher-only REAL MODEL overview</h1>'
        '<p>Eight prescheduled episodes. This privileged view is not agent or auditor input. '
        'Human content labels remain pending. Scripted controls are separate.</p>'
        '<section><h2>Episode schedule</h2><ol>' + "".join(cards) + '</ol></section>'
        '<section><h2>Per-episode counts</h2><pre>' + table + '</pre></section></html>\n',
        encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="One frozen balanced V7 natural study")
    parser.add_argument("--offline-readiness", type=Path, required=True)
    args = parser.parse_args()
    readiness = json.loads(args.offline_readiness.read_text(encoding="utf-8"))
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if readiness.get("offline_gate_pass") is not True or readiness.get("source_commit") != source_commit:
        parser.error("Frozen V7 offline gate/HEAD mismatch; no GPU run")
    source_root = Path(__file__).resolve().parent
    if any(sha((source_root / name).read_bytes()) != expected
           for name, expected in readiness.get("source_sha256", {}).items()):
        parser.error("Frozen V7 source hash mismatch; no GPU run")
    frozen_path = source_root / "researcher_analysis_20261026_v7_live/V7_FROZEN_MANIFEST.json"
    if not frozen_path.is_file():
        parser.error("Machine-readable V7 freeze manifest absent; no GPU run")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if (frozen.get("source_commit_at_generation") != source_commit
            or frozen.get("protocol_version") != PROTOCOL_VERSION
            or frozen.get("agent_visible_initial", {}).get("ordered_tools") != TOOL_SCHEMAS
            or frozen.get("agent_visible_initial", {}).get("tool_schema_sha256") != tool_schema_sha256()
            or frozen.get("source_files_sha256") != readiness.get("source_sha256")):
        parser.error("Frozen V7 manifest/source mismatch; no GPU run")
    import modal_vllm_worker

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(__file__).resolve().parent / "experiments" / f"real_v7_balanced_{timestamp}"
    root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.offline_readiness, root / "V7_OFFLINE_READINESS.json")
    shutil.copy2(frozen_path, root / "V7_FROZEN_MANIFEST.json")
    write_json(root / "run_manifest.json", {
        "protocol_version": PROTOCOL_VERSION, "source_commit": source_commit,
        "provenance": "REAL MODEL after separate SMOKE_NOT_DATA",
        "model": MODEL_NAME, "revision": MODEL_REVISION, "vllm_version": VLLM_VERSION,
        "parser": "hermes", "temperature": TEMPERATURE,
        "block_seeds_requested": BLOCK_SEEDS, "max_generation_tokens": MAX_GENERATION_TOKENS,
        "max_model_len": MAX_MODEL_LEN, "gpu": "Modal L4 x1",
        "schedule": [{"episode_key": f"{i:02d}_{cell}", "block": block, "cell": cell}
                     for i, (block, cell) in enumerate(SCHEDULE, 1)],
        "max_responses_per_agent_episode": MAX_RESPONSES_PER_AGENT,
        "max_study_calls": MAX_STUDY_CALLS, "max_smoke_calls": MAX_SMOKE_CALLS,
        "max_total_calls": MAX_TOTAL_CALLS, "max_gpu_wall_seconds": MAX_GPU_WALL_SECONDS,
        "offline_readiness_sha256": sha(args.offline_readiness.read_bytes()),
        "frozen_manifest_sha256": sha(frozen_path.read_bytes()),
        "tool_schema_sha256": tool_schema_sha256(),
        "prompt_sha256": {cell: {actor: prompt_sha256(actor, WorldV7(cell, run_id="hash").config)
                                 for actor in AGENTS} for cell in CELL_ORDER},
        "status": "STARTING", "episodes_saved": []})
    write_overview(root, [])
    records = []
    validations: dict[str, Any] = {}
    started = time.monotonic()
    transport = None
    smoke = None
    error = None
    stop_technical = False
    try:
        with modal_vllm_worker.app.run():
            worker = modal_vllm_worker.QwenServer()
            worker_info = worker.info.remote()
            write_json(root / "worker_info.json", worker_info)
            ids = [item.get("id") for item in worker_info.get("models", {}).get("data", [])]
            if (worker_info.get("model"), worker_info.get("revision"),
                    worker_info.get("vllm_version")) != (MODEL_NAME, MODEL_REVISION, VLLM_VERSION) or MODEL_NAME not in ids:
                raise RuntimeError("Pinned worker identity mismatch")
            smoke = smoke_interface(worker, root)
            if time.monotonic() - started >= MAX_GPU_WALL_SECONDS:
                raise TimeoutError("Three-hour total GPU-active cap after smoke")
            transport = ModalTransportV7(worker.complete.remote, root / "trusted_provider_calls",
                                         seed=BLOCK_SEEDS[1], max_calls=MAX_STUDY_CALLS,
                                         on_record=lambda receipt: progress(root, {
                                             "kind": "provider_receipt", "actor": receipt["actor"],
                                             "call_number": receipt["call_number"],
                                             "status": receipt["status"]}))
            for index, (block, cell) in enumerate(SCHEDULE, 1):
                if time.monotonic() - started >= MAX_GPU_WALL_SECONDS:
                    raise TimeoutError("Three-hour total GPU-active cap before next episode")
                key = f"{index:02d}_{cell}"
                transport.seed = BLOCK_SEEDS[block]
                record, validation = run_episode(key, block, cell, root, transport,
                                                 source_commit=source_commit, total_started=started)
                records.append(record)
                validations[key] = validation
                write_json(root / "V7_VALIDATION.json", {"episodes": validations,
                          "source_commit": source_commit, "study_calls": transport.call_count})
                write_overview(root, records)
                manifest_path = root / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["episodes_saved"] = [r["episode_key"] for r in records]
                write_json(manifest_path, manifest)
                if record["status"] == "ABORTED" or not validation.get("validation_ok"):
                    stop_technical = True
                    error = f"Episode {key} aborted or failed offline integrity validation"
                    break
    except BaseException as exc:
        stop_technical = True
        error = f"{type(exc).__name__}: {exc}"
        progress(root, {"kind": "run_error", "status": "ABORTED", "error": error}, show=True)
    finally:
        write_json(root / "usage.json", {
            "smoke_calls": smoke["calls"] if smoke else len(list((root / "smoke_provider_calls").glob("*_SMOKE")))
            if (root / "smoke_provider_calls").exists() else 0,
            "study_calls": transport.call_count if transport else 0,
            "token_usage_study": transport.token_usage if transport else None,
            "worker_context_wall_seconds_upper_bound": time.monotonic() - started,
            "billing": "PENDING_READ_ONLY_MODAL_CHECK"})
        manifest_path = root / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "TECHNICAL_STOP" if stop_technical else "COMPLETE_SCHEDULE"
        manifest["error"] = error
        manifest["episodes_saved"] = [r["episode_key"] for r in records]
        manifest["elapsed_wall_seconds"] = time.monotonic() - started
        write_json(manifest_path, manifest)
        write_json(root / "V7_VALIDATION.json", {
            "episodes": validations, "source_commit": source_commit,
            "study_calls": transport.call_count if transport else 0,
            "smoke_pass": smoke is not None,
            "technical_stop": stop_technical, "error": error})
        write_overview(root, records, stopped=stop_technical)
        progress(root, {"kind": "modal_context_exit", "status": "LOCAL_CONTEXT_CLOSED"}, show=True)
        print(f"Researcher index: {root / 'index.html'}", flush=True)
        print(f"PowerShell: Start-Process '{root / 'index.html'}'", flush=True)


if __name__ == "__main__":
    main()
