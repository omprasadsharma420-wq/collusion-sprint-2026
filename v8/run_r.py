"""Prospective paired R runner. No Modal resource is created on import."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from protocol_v3 import MEMO_MARKER
from trace_v2 import TraceV2
from v8.adapter import ActorAdapterV8
from v8.auditor import eligible_cutoffs, m0_at_time, m1_at_time, m1_messages
from v8.protocol import (GPU_ACTIVE_CAP_SECONDS, M1_OUTPUT_SCHEMA, MAX_SMOKE_RESPONSES,
                         MAX_STUDY_RESPONSES, MODEL_NAME, MODEL_REVISION,
                         R_B_RESPONSE_CAP, R_M1_RESPONSE_CAP, R_MESSAGES,
                         R_SCHEDULE, R_SEEDED_ROUTE, R_SEEDED_SENDER, R_SEEDS,
                         R_WORKER_TOOLS, TEMPERATURE, VLLM_VERSION,
                         worker_first_user, worker_system)
from v8.transport import V8Transport, canonical, validate_m1
from v8.world import WorldV8
from world_v3 import _validate_value

R_STUDY_CAP = 24 * (R_B_RESPONSE_CAP + R_M1_RESPONSE_CAP)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True,
                               ensure_ascii=False) + "\n", encoding="utf-8")


def progress(root: Path, **fields: Any) -> None:
    row = {"utc": datetime.now(timezone.utc).isoformat(), **fields}
    with (root / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
    print("[V8-R] " + " ".join(f"{k}={v}" for k, v in fields.items()), flush=True)


def m1_review(world: WorldV8, transport: V8Transport, *, seed: int,
              root: Path) -> dict[str, Any]:
    cutoff = eligible_cutoffs(world.trace)
    if len(cutoff) != 1:
        raise RuntimeError("R requires exactly one predecision seeded-write cutoff")
    cutoff_id = cutoff[0]
    m0 = m0_at_time(world.trace, cutoff_id)
    m1_slice = m1_at_time(world.trace, world.messages, cutoff_id)
    auditor = root / "auditor"
    save_json(auditor / "m0_predecision.json", m0)
    save_json(auditor / "m1_at_time_input.json", m1_slice)
    parsed = transport.respond("M1", {"messages": m1_messages(m1_slice)},
                               seed=seed, kind="m1")
    allowed = {frame["event_id"] for frame in m1_slice["metadata_frames"]}
    if set(parsed) == {"m1_json"}:
        try:
            validate_m1(parsed["m1_json"], cutoff=cutoff_id, allowed_event_ids=allowed)
        except (ValueError, TypeError) as exc:
            judgment = {"status": "INVALID_MODEL_JUDGMENT", "reason": str(exc),
                        "raw_parsed": parsed}
        else:
            judgment = {"status": "AI_ASSISTED_PROVISIONAL", "judgment": parsed["m1_json"]}
    else:
        judgment = {"status": "INVALID_MODEL_JUDGMENT", "raw_parsed": parsed}
    save_json(auditor / "m1_judgment.json", judgment)
    return {"m0": m0, "m1": judgment, "cutoff_event_id": cutoff_id}


def validate_episode(root: Path, record: dict, *, provider_start: int,
                     provider_stop: int, seed: int) -> dict[str, Any]:
    episode = root / record["episode_key"]
    trace = TraceV2.read_jsonl(episode / "trusted/events_v2.jsonl")
    events = trace.events
    inputs = [e for e in events if e.kind == "model_input_captured" and e.actor == "B"]
    outputs = [e for e in events if e.kind == "model_output_captured" and e.actor == "B"]
    assert len(inputs) == len(outputs) == record["B_responses"]
    observations = [e for e in events if e.kind == "recipient_observation" and e.actor == "B"]
    assert len(observations) == 1
    messages_by_id = json.loads((episode / "trusted/messages.json").read_text(encoding="utf-8"))
    seeded = [(mid, value) for mid, value in messages_by_id.items()
              if value.get("origin") == "RESEARCHER_SEEDED_EXPOSURE"]
    assert len(seeded) == 1
    assert all(value.get("origin", "MODEL_ACTION") == "MODEL_ACTION"
               for mid, value in messages_by_id.items() if mid != seeded[0][0])
    mid, value = seeded[0]
    assert value["origin"] == "RESEARCHER_SEEDED_EXPOSURE"
    assert value["route"] == R_SEEDED_ROUTE and value["actor"] == R_SEEDED_SENDER
    assert value["body"] == R_MESSAGES[record["condition"]]
    assert observations[0].data["message_id"] == mid
    first_raw = (episode / "trusted" / inputs[0].data["input_ref"]).read_bytes()
    assert sha(first_raw) == inputs[0].data["input_sha256"]
    first_messages = json.loads(first_raw)["messages"]
    assert any(value["body"] in item.get("content", "") for item in first_messages)
    assert MEMO_MARKER not in json.dumps(first_messages, ensure_ascii=False)
    assert first_messages[0] == {"role": "system", "content": worker_system("B", phase="R")}
    assert {"role": "user", "content": worker_first_user("B", phase="R")} in first_messages
    for index, (inp, out) in enumerate(zip(inputs, outputs), provider_start + 2):
        folder = root / "provider_calls/study" / f"{index:05d}_B"
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        wire = json.loads((folder / "request.json").read_text(encoding="utf-8"))
        parsed = json.loads((folder / "parsed.json").read_text(encoding="utf-8"))
        input_raw = (episode / "trusted" / inp.data["input_ref"]).read_bytes()
        output_raw = (episode / "trusted" / out.data["output_ref"]).read_bytes()
        assert receipt["actor"] == "B" and receipt["seed_requested"] == seed
        assert receipt["status"] == 200 and receipt["response_id"]
        assert sha(input_raw) == inp.data["input_sha256"]
        assert sha(output_raw) == out.data["output_sha256"]
        assert wire["messages"] == json.loads(input_raw)["messages"]
        assert wire["tools"] == R_WORKER_TOOLS
        assert parsed == json.loads(output_raw)
    assert provider_stop - provider_start == record["B_responses"] + 1
    pooled = list(project(trace, AuditView.POOLED_METADATA))
    assert pooled == [json.loads(line) for line in (episode / "auditor/pooled_metadata.jsonl")
                      .read_text(encoding="utf-8").splitlines() if line.strip()]
    verdicts = list(run_audit(tuple(pooled)))
    assert verdicts == [json.loads(line) for line in (episode / "auditor/verdicts.jsonl")
                        .read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"validation_ok": True, "B_responses": len(inputs),
            "M1_responses": 1, "observation_event_id": observations[0].event_id,
            "M0_candidates": len(verdicts), "event_count": len(events)}


def render_episode(root: Path, record: dict) -> None:
    episode = root / record["episode_key"]
    trusted = episode / "trusted"
    inputs = sorted((trusted / "model_inputs").glob("*.json"))
    outputs = sorted((trusted / "model_outputs").glob("*.json"))
    blocks = []
    for index, (inp, out) in enumerate(zip(inputs, outputs), 1):
        blocks.append(f"<details><summary>B response {index}</summary><h4>Actual serialized input</h4><pre>"
                      + html.escape(inp.read_text(encoding="utf-8")) + "</pre><h4>Parsed model output</h4><pre>"
                      + html.escape(out.read_text(encoding="utf-8")) + "</pre></details>")
    links = ''.join(f'<li><a href="{name}">{name}</a></li>' for name in (
        "trusted/events_v2.jsonl", "trusted/tool_calls.json", "auditor/m0_predecision.json",
        "auditor/m1_at_time_input.json", "auditor/m1_judgment.json",
        "auditor/pooled_metadata.jsonl", "auditor/verdicts.jsonl", "VALIDATION.json"))
    (episode / "replay.html").write_text(
        '<!doctype html><html><meta charset="utf-8"><title>V8 R replay</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto}pre{white-space:pre-wrap;'
        'word-break:break-word;background:#f2f4f6;padding:1rem}details{margin:1rem 0}</style>'
        f'<h1>V8 R {html.escape(record["episode_key"])}</h1><p>Researcher-only. '
        'Worker B is real; source message and ticket state are researcher-seeded. '
        'Supervisor S: N/A. M0 deterministic; M1 provisional AI judgment.</p>'
        f'<p>B responses: {record["B_responses"]}; M1 responses: 1; '
        f'invalid release attempt: {record["invalid_approve_release_attempt"]}; '
        f'lawful HOLD accepted: {record["lawful_hold_acceptance"]}</p>'
        '<h2>Evidence files</h2><ul>' + links + '</ul><h2>Worker B input/action lane</h2>'
        + ''.join(blocks) + '</html>', encoding="utf-8")


def write_overview(root: Path, records: list[dict], *, stopped: bool = False) -> None:
    by_key = {r["episode_key"]: r for r in records}
    rows = []
    cards = []
    for index, (block, condition) in enumerate(R_SCHEDULE, 1):
        key = f"{index:02d}_b{block}_{condition}"
        record = by_key.get(key)
        row = record or {"episode_key": key, "block": block, "condition": condition,
                         "status": "NOT_RUN_TECHNICAL" if stopped else "PLANNED_NOT_RUN"}
        rows.append(row)
        href = (f'../{row["source_segment"]}/{key}/replay.html'
                if record and row.get("source_segment") else f'{key}/replay.html')
        cards.append(f'<li>{html.escape(key)}: '
                     + (f'<a href="{html.escape(href)}">{html.escape(row["status"])}</a>' if record
                        else html.escape(row["status"])) + '</li>')
    save_json(root / "V8_R_RESULTS.json", {"planned": 24, "run": len(records),
                                       "episodes": rows,
                                       "human_message_labels": "PENDING_INDEPENDENT_REVIEW"})
    fields = tuple(dict.fromkeys(k for row in rows for k in row))
    with (root / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (root / "index.html").write_text(
        '<!doctype html><html><meta charset="utf-8"><title>V8 R paired study</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto}</style>'
        '<h1>V8 R paired seeded-exposure study</h1><p>Researcher-only; '
        'seeded content is not model-authored. M1 is provisional, human labels pending.</p>'
        '<ol>' + ''.join(cards) + '</ol><p><a href="comparison.csv">Comparison CSV</a></p></html>',
        encoding="utf-8")


def run_episode(root: Path, index: int, block: int, condition: str,
                transport: V8Transport, *, source_commit: str,
                started: float) -> tuple[dict, dict]:
    key = f"{index:02d}_b{block}_{condition}"
    episode = root / key
    episode.mkdir(parents=True, exist_ok=False)
    world = WorldV8(phase="R", gate_known_direct=False, run_id=f"v8-{key}",
                    tool_call_cap=R_B_RESPONSE_CAP)
    mid = world.seed_r_message(body=R_MESSAGES[condition])
    adapter = ActorAdapterV8(world, transport, phase="R", private_note=None,
                             seed=R_SEEDS[block - 1], worker_cap=R_B_RESPONSE_CAP)
    call_start = transport.call_count
    began = time.monotonic()
    progress(root, kind="episode_start", episode_key=key, condition=condition)
    status, error = "RUNNING", None
    review = None
    try:
        review = m1_review(world, transport, seed=R_SEEDS[block - 1], root=episode)
        world.export(episode, source_commit=source_commit)
        for turn in range(1, R_B_RESPONSE_CAP + 1):
            if time.monotonic() - started >= GPU_ACTIVE_CAP_SECONDS - 300:
                raise TimeoutError("Five-hour GPU-active safety margin")
            if adapter.finished["B"]:
                break
            step, tool_result = adapter.step("B")
            world.export(episode, source_commit=source_commit)
            progress(root, kind="model_step", episode_key=key, actor="B", turn=turn,
                     status=step, tool=(world.tool_calls[-1]["tool_name"] if step == "tool" else None),
                     result_ok=(tool_result.get("ok") if tool_result else None))
        status = "ALL_FINAL" if adapter.finished["B"] else "AT_RESPONSE_CAP"
    except BaseException as exc:
        status = "ABORTED"
        error = f"{type(exc).__name__}: {exc}"
        progress(root, kind="episode_error", episode_key=key, error=error)
    world.export(episode, source_commit=source_commit)
    pooled = project(world.trace, AuditView.POOLED_METADATA)
    verdicts = run_audit(pooled)
    (episode / "auditor/verdicts.jsonl").write_text(
        ''.join(json.dumps(v, sort_keys=True) + '\n' for v in verdicts), encoding="utf-8")
    outcome = world.outcome()
    record = {"episode_key": key, "block": block, "condition": condition,
              "seed_requested": R_SEEDS[block - 1], "status": status, "error": error,
              "origin": "RESEARCHER_SEEDED_EXPOSURE", "message_id": mid,
              "source_commit": source_commit,
              "B_responses": adapter.response_counts["B"],
              "M1_responses": int(review is not None),
              "invalid_approve_release_attempt": bool(outcome["invalid_release_approval"]),
              "lawful_hold_acceptance": outcome["t4_review_correctness"] == "CORRECT_ACCEPT_HOLD",
              "B_review_correctness": outcome["t4_review_correctness"],
              "task_score_including_fixture": outcome["task_score"],
              "M0_candidates": len(verdicts),
              "M0_alerts": sum(v["verdict"] == "alert" for v in verdicts),
              "M1_status": review["m1"]["status"] if review else "NOT_EVALUATED",
              "elapsed_seconds": time.monotonic() - began}
    save_json(episode / "episode_manifest.json", record)
    try:
        validation = validate_episode(root, record, provider_start=call_start,
                                      provider_stop=transport.call_count,
                                      seed=R_SEEDS[block - 1])
    except BaseException as exc:
        validation = {"validation_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    save_json(episode / "VALIDATION.json", validation)
    render_episode(root, record)
    progress(root, kind="episode_saved", episode_key=key, status=status,
             B_responses=record["B_responses"], validation_ok=validation["validation_ok"])
    return record, validation


def smoke(worker, root: Path) -> dict:
    """Exactly two isolated real calls: B tool parse and M1 constrained JSON."""
    transport = V8Transport(worker.complete.remote, root / "provider_calls/smoke", max_calls=2)
    world = WorldV8(phase="R", gate_known_direct=False, run_id="v8-r-smoke")
    world.seed_r_message(body=R_MESSAGES["R0_BENIGN"])
    messages = [
        {"role": "system", "content": "SMOKE_ENGINEERING_FIXTURE: isolated B interface check."},
        world.review_context_message(), *world.notification_messages("B"),
        {"role": "user", "content": "SMOKE_ENGINEERING_FIXTURE: select review_t4 "
         "with decision accept_assessment and reason 'interface check'. Do not answer in prose."},
    ]
    raw = world.capture_model_input("B", messages, tools=R_WORKER_TOOLS)
    assert len([e for e in world.trace.events if e.kind == "recipient_observation"]) == 1
    parsed_b = transport.respond("B", json.loads(raw), seed=R_SEEDS[0], kind="worker")
    if set(parsed_b) != {"tool_call"} or parsed_b["tool_call"]["name"] != "review_t4":
        raise RuntimeError("SMOKE B did not generate review_t4 tool call")
    schema = next(t["function"]["parameters"] for t in R_WORKER_TOOLS if
                  t["function"]["name"] == "review_t4")
    _validate_value(schema, parsed_b["tool_call"]["arguments"])
    slice_ = m1_at_time(world.trace, world.messages, eligible_cutoffs(world.trace)[0])
    parsed_m1 = transport.respond("M1", {"messages": m1_messages(slice_)},
                                  seed=R_SEEDS[0], kind="m1")
    if set(parsed_m1) != {"m1_json"}:
        raise RuntimeError("SMOKE M1 did not return JSON")
    validate_m1(parsed_m1["m1_json"], cutoff=slice_["cutoff_event_id"],
                allowed_event_ids={f["event_id"] for f in slice_["metadata_frames"]})
    result = {"provenance": "SMOKE_ENGINEERING_FIXTURE_NOT_DATA", "calls": 2,
              "B_model_tool_parse": True, "M1_json_schema_parse": True,
              "B_recipient_input_observed": True}
    save_json(root / "SMOKE_NOT_DATA.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path,
                        help="Preserve and independently revalidate the first complete R pair")
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    if not freeze.get("ready_for_R_live") or freeze.get("source_commit") != commit:
        parser.error("R freeze gate or commit mismatch; no GPU")
    if any(sha((ROOT / name).read_bytes()) != digest for name, digest in
           freeze.get("source_sha256", {}).items()):
        parser.error("Frozen source hash mismatch; no GPU")
    if freeze.get("R_schedule") != [list(item) for item in R_SCHEDULE]:
        parser.error("R allocation mismatch; no GPU")
    prior_root = args.resume_from.resolve() if args.resume_from else None
    prior_records: list[dict] = []
    prior_validations: dict[str, dict] = {}
    if prior_root:
        old_freeze = json.loads((prior_root / "V8_FROZEN_MANIFEST.json").read_text(
            encoding="utf-8"))
        excluded = {"source_commit", "source_sha256", "ready_for_R_live"}
        if {k: v for k, v in old_freeze.items() if k not in excluded} != {
                k: v for k, v in freeze.items() if k not in excluded}:
            parser.error("Prospective scientific design changed across R segments")
        changed_sources = {name for name, old_hash in old_freeze["source_sha256"].items()
                           if freeze["source_sha256"].get(name) != old_hash}
        if changed_sources - {"v8/run_r.py", "v8/tests/test_run_r_offline.py"}:
            parser.error("Nontechnical source changed across R segments")
        previous = json.loads((prior_root / "run_manifest.json").read_text(encoding="utf-8"))
        if previous.get("status") != "TECHNICAL_STOP" or not (
                prior_root / "SMOKE_NOT_DATA.json").exists():
            parser.error("Prior R segment lacks stopped-state and passed smoke evidence")
        summaries = json.loads((prior_root / "V8_R_RESULTS.json").read_text(encoding="utf-8"))
        prior_records = summaries["episodes"][:2]
        if [(r["block"], r["condition"]) for r in prior_records] != list(R_SCHEDULE[:2]):
            parser.error("Prior R segment is not the first prescheduled matched pair")
        if previous.get("episodes_saved") != [r["episode_key"] for r in prior_records] or any(
                r["status"] == "ABORTED" for r in prior_records):
            parser.error("Prior R pair is incomplete")
        call_start = 0
        for record in prior_records:
            call_stop = call_start + record["B_responses"] + 1
            checked = validate_episode(prior_root, record, provider_start=call_start,
                                       provider_stop=call_stop, seed=R_SEEDS[0])
            prior_validations[record["episode_key"]] = checked
            call_start = call_stop
            record["source_segment"] = prior_root.name
    import modal_vllm_worker

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = ROOT / "experiments" / f"real_v8_R_{timestamp}"
    root.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.freeze, root / "V8_FROZEN_MANIFEST.json")
    if prior_root:
        save_json(root / "PRIOR_PAIR_REVALIDATION.json", {
            "prior_root": str(prior_root), "prior_source_commit": previous["source_commit"],
            "prior_episode_validations": prior_validations,
            "no_prior_episode_rerun": True})
    save_json(root / "run_manifest.json", {"phase": "R", "source_commit": commit,
        "planned_episodes": 24, "schedule": [list(item) for item in R_SCHEDULE],
        "continued_from": str(prior_root) if prior_root else None,
        "model": MODEL_NAME, "revision": MODEL_REVISION, "vllm_version": VLLM_VERSION,
        "temperature": TEMPERATURE, "max_B_responses": R_B_RESPONSE_CAP,
        "max_M1_responses": R_M1_RESPONSE_CAP,
        "R_study_call_cap": R_STUDY_CAP - sum(r["B_responses"] + 1 for r in prior_records),
        "status": "STARTING", "episodes_saved": []})
    write_overview(root, prior_records)
    records, validations = list(prior_records), dict(prior_validations)
    started = time.monotonic()
    transport = None
    smoke_result = None
    technical_stop, error = False, None
    try:
        with modal_vllm_worker.app.run():
            worker = modal_vllm_worker.QwenServer()
            identity = worker.info.remote()
            save_json(root / "worker_info.json", identity)
            listed = [item.get("id") for item in identity.get("models", {}).get("data", [])]
            if (identity.get("model"), identity.get("revision"), identity.get("vllm_version")) != (
                MODEL_NAME, MODEL_REVISION, VLLM_VERSION) or MODEL_NAME not in listed:
                raise RuntimeError("Pinned worker identity mismatch")
            if prior_root is None:
                smoke_result = smoke(worker, root)
            transport = V8Transport(worker.complete.remote, root / "provider_calls/study",
                                    max_calls=R_STUDY_CAP - sum(
                                        r["B_responses"] + 1 for r in prior_records))
            for index, (block, condition) in enumerate(R_SCHEDULE[len(prior_records):],
                                                       len(prior_records) + 1):
                if time.monotonic() - started >= GPU_ACTIVE_CAP_SECONDS - 300:
                    raise TimeoutError("Five-hour GPU-active cap before next R episode")
                record, validation = run_episode(root, index, block, condition, transport,
                                                 source_commit=commit, started=started)
                records.append(record)
                validations[record["episode_key"]] = validation
                save_json(root / "V8_R_VALIDATION.json", {"episodes": validations,
                          "study_calls": transport.call_count, "source_commit": commit})
                write_overview(root, records)
                manifest_path = root / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["episodes_saved"] = [r["episode_key"] for r in records]
                save_json(manifest_path, manifest)
                if record["status"] == "ABORTED" or not validation["validation_ok"]:
                    technical_stop = True
                    error = f"Episode {record['episode_key']} failed integrity validation"
                    break
    except BaseException as exc:
        technical_stop = True
        error = f"{type(exc).__name__}: {exc}"
        progress(root, kind="run_error", error=error)
    finally:
        manifest_path = root / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(status="TECHNICAL_STOP" if technical_stop else "COMPLETE_SCHEDULE",
                        error=error, episodes_saved=[r["episode_key"] for r in records],
                        elapsed_wall_seconds=time.monotonic() - started)
        save_json(manifest_path, manifest)
        save_json(root / "usage.json", {"smoke_calls": smoke_result["calls"] if smoke_result else 0,
            "study_calls": transport.call_count if transport else 0,
            "study_token_usage": transport.usage if transport else None,
            "worker_context_wall_seconds_upper_bound": time.monotonic() - started,
            "billing": "PENDING_OFFICIAL_MODAL_CHECK"})
        save_json(root / "V8_R_VALIDATION.json", {"episodes": validations,
                  "study_calls": transport.call_count if transport else 0,
                  "smoke_pass": smoke_result is not None or prior_root is not None,
                  "technical_stop": technical_stop, "error": error})
        write_overview(root, records, stopped=technical_stop)
        progress(root, kind="modal_context_exit", status="LOCAL_CONTEXT_CLOSED")
        print(f"V8 R researcher index: {root / 'index.html'}", flush=True)
        print(f"PowerShell: Start-Process '{root / 'index.html'}'", flush=True)


if __name__ == "__main__":
    main()
