"""Read-only forensic export from the immutable real pilot records.

This script creates derived researcher tables. It never imports a model transport,
edits canonical episode data, or assigns human policy labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parents[1]
SIM = HERE.parents[3]
sys.path.insert(0, str(SIM))

from audit_projection_v2 import AuditView, project
from audit_rules_v3 import run_audit
from protocol_v3 import AGENTS, ANSWER_KEYS, MEMO_MARKER, TOOL_SCHEMAS, CellConfig, prompt_sha256
from trace_v2 import TraceV2
from world_v3 import verify_findings

SEED = 772025
CELL_ORDER = "CADB"
ROUTES = ("known_direct", "team_board", "release_checklist")
EVENT_KINDS = ("attempt", "authorization_denial", "accepted_write",
               "recipient_delivery", "recipient_observation", "agent_discovery_report")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def event_for(events: list[dict], kind: str, call_id: str) -> dict:
    found = [e for e in events if e["kind"] == kind and e["data"].get("call_id") == call_id]
    assert len(found) == 1, (kind, call_id)
    return found[0]


def last_visible_ticket_snapshot(request: dict) -> str:
    for message in reversed(request["messages"]):
        if message.get("role") == "tool" and message.get("name") == "list_tickets":
            result = json.loads(message["content"])
            return "; ".join(
                f'{t["ticket_id"]}:{t["owner"] or "-"}'
                f'/{int(t["evidence_accepted"])}/{int(t["analysis_declared"])}'
                for t in result["tickets"]
            )
    return "none yet"


def main() -> None:
    assert read_json(RUN / "run_manifest.json")["cells_saved"] == list(CELL_ORDER)
    assert read_json(RUN / "run_manifest.json")["commit"] == (
        "d16ec98a46332d9d01836d2f7a4fb451bbb68630")
    provider_folders = sorted((RUN / "trusted_provider_calls").iterdir())
    assert len(provider_folders) == 193
    provider_rows = []
    response_ids = set()
    for folder in provider_folders:
        receipt = read_json(folder / "receipt.json")
        assert receipt["status"] == 200
        assert digest(folder / "request.json") == receipt["request_sha256"]
        assert digest(folder / "response.json") == receipt["response_sha256"]
        assert receipt["response_id"] not in response_ids
        response_ids.add(receipt["response_id"])
        request = read_json(folder / "request.json")
        assert request["tools"] == TOOL_SCHEMAS
        assert request["temperature"] == 0 and request["seed"] == 4187
        assert request["chat_template_kwargs"] == {"enable_thinking": False}
        number = receipt["call_number"]
        cell = ("SMOKE" if number == 1 else
                "C" if number <= 49 else
                "A" if number <= 97 else
                "D" if number <= 145 else "B")
        provider_rows.append({
            "provider_call_number": number, "cell": cell,
            "segment": "LIVE SMOKE" if receipt["actor"] == "SMOKE" else "REAL MODEL",
            "actor": receipt["actor"],
            "response_id": receipt["response_id"],
            "request_sha256": receipt["request_sha256"],
            "response_sha256": receipt["response_sha256"],
            "model": receipt["model"],
            "revision": receipt["revision"],
            "vllm_version": receipt["vllm_version"],
            "prompt_tokens": receipt["usage"]["prompt_tokens"],
            "completion_tokens": receipt["usage"]["completion_tokens"],
        })
    assert len(response_ids) == 193
    write_csv(HERE / "PROVIDER_CALLS.csv", provider_rows, list(provider_rows[0]))
    provider_counts = [
        {"cell": cell, "agent": actor,
         "calls": sum(row["cell"] == cell and row["actor"] == actor for row in provider_rows),
         "unique_response_ids": len({row["response_id"] for row in provider_rows
                                     if row["cell"] == cell and row["actor"] == actor})}
        for cell in "ABCD" for actor in AGENTS
    ]
    assert all(row["calls"] == row["unique_response_ids"] == 12 for row in provider_counts)
    write_csv(HERE / "PROVIDER_COUNTS.csv", provider_counts, list(provider_counts[0]))
    hashed_paths = [
        SIM / name for name in (
            "protocol_v3.py", "world_v3.py", "audit_rules_v3.py",
            "audit_projection_v2.py", "agent_adapter_v3.py",
            "modal_transport.py", "PROMPT_HASHES_V3.json")
    ] + [
        RUN / name for name in (
            "run_manifest.json", "usage.json", "smoke.json", "VALIDATION.json",
            "comparison.csv", "MODAL_STOP_VERIFICATION.json")
    ]
    for cell in "ABCD":
        hashed_paths += [
            RUN / cell / name for name in (
                "manifest.json", "trusted/events_v2.jsonl", "trusted/tool_calls.json",
                "trusted/outcome.json", "trusted/messages.json",
                "auditor/pooled_metadata.jsonl", "auditor/verdicts.jsonl",
                "researcher/replay.html")
        ]
    hash_rows = [{
        "path_relative_to_sim": path.relative_to(SIM).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": digest(path),
    } for path in hashed_paths]
    write_csv(HERE / "HASH_MANIFEST.csv", hash_rows, list(hash_rows[0]))
    frozen_commit = "d16ec98a46332d9d01836d2f7a4fb451bbb68630"
    frozen_names = (
        "protocol_v3.py", "world_v3.py", "audit_rules_v3.py",
        "audit_projection_v2.py", "agent_adapter_v3.py",
        "modal_transport.py", "modal_vllm_worker.py",
        "run_real_modal.py", "render_trace.py", "PROMPT_HASHES_V3.json",
    )
    frozen_rows = []
    for name in frozen_names:
        repository_path = f"collective-blind-spot-sim/{name}"
        blob = subprocess.check_output(
            ["git", "show", f"{frozen_commit}:{repository_path}"], cwd=SIM.parent)
        current = (SIM / name).read_bytes()
        frozen_rows.append({
            "source_commit": frozen_commit, "repository_path": repository_path,
            "frozen_git_blob_size_bytes": len(blob),
            "frozen_git_blob_sha256": hashlib.sha256(blob).hexdigest(),
            "current_worktree_size_bytes": len(current),
            "current_worktree_sha256": hashlib.sha256(current).hexdigest(),
            "content_diff_from_frozen_commit": int(
                bool(subprocess.check_output(
                    ["git", "diff", "--name-only", frozen_commit, "HEAD", "--",
                     repository_path], cwd=SIM.parent).strip())),
        })
    write_csv(HERE / "FROZEN_SOURCE_HASHES.csv", frozen_rows, list(frozen_rows[0]))

    index_path = RUN / "index.html"
    parser = LinkParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    missing = [link for link in parser.links if not (index_path.parent / link).exists()]
    assert not missing and len(parser.links) == 7
    replay_checks = {"index_path": str(index_path), "index_links": len(parser.links),
                     "missing_index_links": missing, "cells": {}}
    for cell in "ABCD":
        html = (RUN / cell / "researcher/replay.html").read_text(encoding="utf-8")
        required = (
            "REAL MODEL — CAPTURED RUN", "Global chronological event stream",
            "Independent monitor input: exact pooled metadata frames",
            "Independent monitor verdicts", "RESEARCHER-ONLY TRUTH",
            "model_inputs/0001.json", "model_outputs/0001.json",
        )
        absent = [item for item in required if item not in html]
        assert not absent, (cell, absent)
        replay_checks["cells"][cell] = {"all_required_panels_present": True,
                                        "absent_items": absent}
    (HERE / "REPLAY_CHECKS.json").write_text(
        json.dumps(replay_checks, indent=2) + "\n", encoding="utf-8")

    turn_rows: list[dict] = []
    aggregate_rows: list[dict] = []
    submit_rows: list[dict] = []
    verifier_rows: list[dict] = []
    message_link_rows: list[dict] = []
    message_chains: list[dict] = []
    route_rows: list[dict] = []
    monitor_rows: list[dict] = []
    cell_summaries: dict = {}
    all_messages: list[dict] = []
    provider_start = {"C": 2, "A": 50, "D": 98, "B": 146}
    audit_dir = HERE / "evidence" / "auditor"
    audit_dir.mkdir(parents=True, exist_ok=True)

    for cell in CELL_ORDER:
        cell_root = RUN / cell
        manifest = read_json(cell_root / "manifest.json")
        assert manifest["provenance"] == "REAL MODEL"
        assert manifest["model_calls"] == 48
        assert manifest["actor_response_counts"] == {a: 12 for a in AGENTS}
        assert manifest["prompt_sha256"] == {
            a: prompt_sha256(a, CellConfig.for_cell(cell)) for a in AGENTS}
        trace = TraceV2.read_jsonl(cell_root / "trusted" / "events_v2.jsonl")
        events = [e.as_dict() for e in trace.events]
        calls = read_json(cell_root / "trusted" / "tool_calls.json")
        messages = read_json(cell_root / "trusted" / "messages.json")
        assert len(calls) == 48
        assert list(messages) == [f"m{i:04d}" for i in range(1, len(messages) + 1)]
        input_events = [e for e in events if e["kind"] == "model_input_captured"]
        output_events = [e for e in events if e["kind"] == "model_output_captured"]
        assert len(input_events) == len(output_events) == 48
        pooled = project(trace, AuditView.POOLED_METADATA)
        assert list(pooled) == read_lines(cell_root / "auditor" / "pooled_metadata.jsonl")
        verdicts = run_audit(pooled)
        assert list(verdicts) == read_lines(cell_root / "auditor" / "verdicts.jsonl")
        for actor in AGENTS:
            assert list(project(trace, AuditView.LOCAL, actor=actor)) == read_lines(
                cell_root / "auditor" / f"local_{actor}.jsonl")
        shutil.copyfile(cell_root / "auditor" / "pooled_metadata.jsonl",
                        audit_dir / f"{cell}_pooled_input.jsonl")
        shutil.copyfile(cell_root / "auditor" / "verdicts.jsonl",
                        audit_dir / f"{cell}_verdicts.jsonl")
        assert MEMO_MARKER not in (audit_dir / f"{cell}_pooled_input.jsonl").read_text(
            encoding="utf-8")
        for verdict in verdicts:
            cutoff = verdict["decision_seq"]
            frame = next(f for f in pooled if f["seq"] == cutoff)
            monitor_rows.append({
                "cell": cell, "monitor_event_id": verdict["event_id"],
                "cutoff_seq": cutoff, "candidate_frame": dump(frame),
                "input_prefix_file": f"evidence/auditor/{cell}_pooled_input.jsonl",
                "rule_id": verdict["rule_id"], "verdict": verdict["verdict"],
                "evidence_event_ids": ";".join(verdict["evidence_event_ids"]),
                "reason": verdict["reason"],
            })
        prior_ticket_owner: dict[str, str] = {}
        actor_turns = Counter()
        previous_action = defaultdict(Counter)
        for index, call in enumerate(calls):
            actor = call["actor"]
            actor_turns[actor] += 1
            own_turn = actor_turns[actor]
            input_event = input_events[index]
            output_event = output_events[index]
            invocation = event_for(events, "tool_invocation", call["call_id"])
            tool_result = event_for(events, "tool_result", call["call_id"])
            assert input_event["actor"] == output_event["actor"] == actor
            assert input_event["seq"] < output_event["seq"] < invocation["seq"] < tool_result["seq"]
            input_ref = input_event["data"]["input_ref"]
            output_ref = output_event["data"]["output_ref"]
            request_path = cell_root / "trusted" / input_ref
            output_path = cell_root / "trusted" / output_ref
            assert digest(request_path) == input_event["data"]["input_sha256"]
            assert digest(output_path) == output_event["data"]["output_sha256"]
            request = read_json(request_path)
            output = read_json(output_path)
            assert output["tool_call"]["name"] == call["tool_name"]
            assert output["tool_call"]["arguments"] == call["arguments"]
            provider_number = provider_start[cell] + index
            receipt = read_json(provider_folders[provider_number - 1] / "receipt.json")
            assert receipt["actor"] == actor and receipt["call_number"] == provider_number
            assert receipt["response_id"] in response_ids
            ticket = call["arguments"].get("ticket_id", "")
            server_owners_before = ";".join(
                f"{t}:{prior_ticket_owner.get(t, '-')}" for t in ("T1", "T2", "T3", "T4"))
            next_index = next(
                (j for j in range(index + 1, 48) if calls[j]["actor"] == actor), None)
            next_ref = (input_events[next_index]["data"]["input_ref"]
                        if next_index is not None else "NONE: fixed 12-response cap")
            next_contains_result = ""
            if next_index is not None:
                next_request = read_json(cell_root / "trusted" / next_ref)
                call_model_id = output["tool_call"]["id"]
                matches = [m for m in next_request["messages"]
                           if m.get("role") == "tool" and m.get("tool_call_id") == call_model_id]
                assert len(matches) == 1
                assert json.loads(matches[0]["content"]) == call["result"]
                next_contains_result = "yes"
            visible_artifacts = set()
            for message in request["messages"]:
                if message.get("role") != "tool":
                    continue
                try:
                    result = json.loads(message["content"])
                except json.JSONDecodeError:
                    continue
                if result.get("ok") and "artifact" in result and result.get("ticket_id"):
                    visible_artifacts.add(result["ticket_id"])
            result = call["result"]
            name = call["tool_name"]
            repeated = previous_action[actor][(name, dump(call["arguments"]))] > 0
            previous_action[actor][(name, dump(call["arguments"]))] += 1
            if name == "assign_ticket" and result.get("ok"):
                progress = f"claimed {ticket}"
            elif name == "read_ticket_artifact" and result.get("ok"):
                progress = f"artifact returned for {ticket}; visible in next own model input"
            elif name == "submit_work" and not result.get("ok"):
                progress = f"submission rejected: {result.get('reason')}"
            elif name == "submit_work":
                progress = "evidence accepted"
            elif name == "declare_complete":
                progress = "declared" if result.get("ok") else "declaration rejected"
            elif name in ("send_direct", "post_team_update", "update_release_checklist"):
                progress = "write accepted" if result.get("ok") else "write denied"
            elif not result.get("ok"):
                progress = f"no progress: {result.get('reason', 'rejected')}"
            else:
                progress = "read/report; no ticket completion"
            row = {
                "cell": cell, "agent": actor, "agent_turn": own_turn,
                "cell_call_index": index + 1, "provider_call_number": provider_number,
                "provider_response_id": receipt["response_id"],
                "input_event_id": input_event["event_id"], "input_ref": input_ref,
                "output_event_id": output_event["event_id"], "output_ref": output_ref,
                "tool_call_id": call["call_id"], "tool_event_id": invocation["event_id"],
                "tool_result_event_id": tool_result["event_id"],
                "tool": name, "arguments_json": dump(call["arguments"]),
                "result_json": dump(result), "result_ok": result.get("ok", ""),
                "result_reason": result.get("reason", ""),
                "last_visible_list_tickets": last_visible_ticket_snapshot(request),
                "visible_artifacts": ";".join(sorted(visible_artifacts)),
                "trusted_owners_before": server_owners_before,
                "progress": progress, "exact_repeat_by_actor": int(repeated),
                "next_own_input_ref": next_ref,
                "next_input_contains_this_result": next_contains_result,
            }
            turn_rows.append(row)
            if name == "submit_work":
                e = [e for e in events if e["kind"] == "evidence_verified"
                     and e["data"].get("ticket_id") == ticket
                     and invocation["event_id"] in e["parent_event_ids"]]
                assert len(e) == 1
                submit_rows.append({
                    "cell": cell, "agent": actor, "agent_turn": own_turn,
                    "tool_call_id": call["call_id"],
                    "tool_invocation_event_id": invocation["event_id"],
                    "evidence_event_id": e[0]["event_id"],
                    "ticket_id": ticket, "findings_json": dump(call["arguments"]["findings"]),
                    "accepted": int(result["ok"]), "reason": result.get("reason", ""),
                    "artifact_visible_in_input": int(ticket in visible_artifacts),
                    "input_ref": input_ref, "result_event_id": tool_result["event_id"],
                })
                offline_verdict = verify_findings(ticket, call["arguments"]["findings"])
                assert offline_verdict["accepted"] == bool(result["ok"])
                assert offline_verdict["reason"] == result["reason"]
                verifier_rows.append({
                    "cell": cell, "tool_call_id": call["call_id"], "ticket_id": ticket,
                    "actual_normalized_json": dump(offline_verdict["normalized"]),
                    "expected_answer_json_RESEARCHER_ONLY": dump(ANSWER_KEYS[ticket]),
                    "exact_match": int(offline_verdict["accepted"]),
                    "recorded_result_reason": result["reason"],
                })
            if name == "assign_ticket" and result.get("ok"):
                prior_ticket_owner[ticket] = actor
        assert actor_turns == {a: 12 for a in AGENTS}
        counts = Counter(c["tool_name"] for c in calls)
        assert set(counts) <= {tool["function"]["name"] for tool in TOOL_SCHEMAS}
        for name in (t["function"]["name"] for t in TOOL_SCHEMAS):
            subset = [c for c in calls if c["tool_name"] == name]
            aggregate_rows.append({
                "cell": cell, "tool": name, "calls": len(subset),
                "accepted_ok": sum(bool(c["result"].get("ok")) for c in subset),
                "rejected": sum(not bool(c["result"].get("ok")) for c in subset),
                "exact_repeats_after_first": sum(
                    int(r["exact_repeat_by_actor"]) for r in turn_rows
                    if r["cell"] == cell and r["tool"] == name),
            })
        attempts = [e for e in events if e["kind"] == "attempt"]
        assert len(attempts) == len(messages)
        for route in ROUTES:
            mids = {m["message_id"] for m in messages.values() if m["route"] == route}
            route_rows.append({
                "cell": cell, "route": route, "attempts": len(mids),
                "denied": sum(e["kind"] == "authorization_denial"
                              and e["data"].get("message_id") in mids for e in events),
                "accepted": sum(e["kind"] == "accepted_write"
                                and e["data"].get("message_id") in mids for e in events),
                "deliveries": sum(e["kind"] == "recipient_delivery"
                                  and e["data"].get("message_id") in mids for e in events),
                "observations": sum(e["kind"] == "recipient_observation"
                                    and e["data"].get("message_id") in mids for e in events),
                "pending_content_labels": len(mids),
            })
        for message_id, message in messages.items():
            attempt = [e for e in attempts if e["data"]["message_id"] == message_id]
            assert len(attempt) == 1
            assert message["body"] in dump(calls)
            event = attempt[0]
            sending_call = next(c for c in calls if c["actor"] == message["actor"]
                                and c["tool_name"] in (
                                    "send_direct", "post_team_update", "update_release_checklist")
                                and message["body"] in dump(c["arguments"]))
            invocation = event_for(events, "tool_invocation", sending_call["call_id"])
            prior_results = [e for e in events if e["kind"] == "tool_result"
                             and e["actor"] == message["actor"] and e["seq"] < event["seq"]]
            prior_result = prior_results[-1] if prior_results else None
            preceding_call = next(
                (c for c in calls if prior_result and c["call_id"] ==
                 prior_result["data"]["call_id"]), None)
            context = ("No earlier own tool result" if not preceding_call else
                       f'Previous own tool: {preceding_call["tool_name"]}'
                       f'({preceding_call["arguments"].get("ticket_id", "")}) returned '
                       f'{"ok" if preceding_call["result"].get("ok") else preceding_call["result"].get("reason", "rejected")}.')
            delivery_events = [e for e in events if e["kind"] == "recipient_delivery"
                               and e["data"]["message_id"] == message_id]
            observation_events = [e for e in events if e["kind"] == "recipient_observation"
                                  and e["data"]["message_id"] == message_id]
            link = {
                "cell": cell, "message_id": message_id,
                "attempt_event_id": event["event_id"],
                "tool_call_id": sending_call["call_id"],
                "tool_invocation_event_id": invocation["event_id"],
                "route": message["route"], "sender": message["actor"],
                "intended_recipients": ";".join(message["recipients"]),
                "accepted": int(message["accepted"]),
                "delivery_event_ids": ";".join(e["event_id"] for e in delivery_events),
                "observation_event_ids": ";".join(e["event_id"] for e in observation_events),
                "observing_peer_inputs": ";".join(
                    f'{e["data"]["recipient"]}:{e["data"]["model_input_ref"]}'
                    for e in observation_events),
                "raw_body": message["body"],
                "prior_context": context,
                "prior_tool_result_event_id": prior_result["event_id"] if prior_result else "",
            }
            message_link_rows.append(link)
            all_messages.append(link)
            chain = [
                e for e in events if e["data"].get("message_id") == message_id
                and e["kind"] in {
                    "attempt", "authorization_denial", "accepted_write",
                    "recipient_delivery", "recipient_observation"}
            ]
            assert chain and chain[0]["kind"] == "attempt"
            message_chains.append({
                "cell": cell, "message_id": message_id,
                "tool_call_id": sending_call["call_id"],
                "tool_invocation_event": invocation,
                "message_events": chain,
            })
        cell_summaries[cell] = {
            "events": len(events), "model_calls": len(calls),
            "tool_counts": dict(counts),
            "submit_work_attempts": counts["submit_work"],
            "submit_work_accepted": sum(c["tool_name"] == "submit_work"
                                        and c["result"].get("ok") for c in calls),
            "assign_accepted": sum(c["tool_name"] == "assign_ticket"
                                   and c["result"].get("ok") for c in calls),
            "assign_rejected": sum(c["tool_name"] == "assign_ticket"
                                   and not c["result"].get("ok") for c in calls),
            "report_concern": counts["report_concern"],
            "no_final_outputs": all("tool_call" in read_json(
                cell_root / "trusted" / e["data"]["output_ref"]) for e in output_events),
            "invalid_tool_names": 0,
            "pooled_frames": len(pooled), "monitor_verdicts": len(verdicts),
            "task_score": read_json(cell_root / "trusted" / "outcome.json")["task_score"],
            "pending_review": len(messages),
        }
    assert len(turn_rows) == 192 and len(message_link_rows) == 14
    assert len(submit_rows) == 23
    write_csv(HERE / "TURN_BY_TURN.csv", turn_rows, list(turn_rows[0]))
    write_csv(HERE / "TOOL_AGGREGATES.csv", aggregate_rows, list(aggregate_rows[0]))
    stage_rows = []
    for cell in "ABCD":
        for actor in AGENTS:
            own = [row for row in turn_rows if row["cell"] == cell and row["agent"] == actor]
            claim = next(row for row in own if row["tool"] == "assign_ticket"
                         and row["result_ok"] is True)
            assigned_ticket = read_json(RUN / cell / "trusted" / claim["output_ref"])[
                "tool_call"]["arguments"]["ticket_id"]
            artifact = next(row for row in own if row["tool"] == "read_ticket_artifact"
                            and row["result_ok"] is True)
            submissions = [row for row in own if row["tool"] == "submit_work"]
            declarations = [row for row in own if row["tool"] == "declare_complete"]
            reviews = [row for row in own if row["tool"] == "review_t4"]
            stage_rows.append({
                "cell": cell, "agent": actor, "model_responses": len(own),
                "claimed_ticket": assigned_ticket,
                "accepted_claim_call_event": f'{claim["tool_call_id"]}/{claim["tool_event_id"]}',
                "first_artifact_call_event": f'{artifact["tool_call_id"]}/{artifact["tool_event_id"]}',
                "artifact_seen_in_subsequent_input": int(any(
                    assigned_ticket in row["visible_artifacts"].split(";")
                    for row in own if int(row["agent_turn"]) > int(artifact["agent_turn"]))),
                "candidate_finding_formed": int(bool(submissions)),
                "submit_attempts": len(submissions),
                "submit_call_event_ids": ";".join(
                    f'{row["tool_call_id"]}/{row["tool_event_id"]}' for row in submissions),
                "submit_accepted": sum(row["result_ok"] is True for row in submissions),
                "declare_attempts": len(declarations),
                "declare_accepted": sum(row["result_ok"] is True for row in declarations),
                "t4_review_attempts": len(reviews),
                "last_call_event": f'{own[-1]["tool_call_id"]}/{own[-1]["tool_event_id"]}',
                "last_action": own[-1]["tool"],
            })
    assert len(stage_rows) == 16
    write_csv(HERE / "AGENT_STAGE_MATRIX.csv", stage_rows, list(stage_rows[0]))
    write_csv(HERE / "evidence" / "SUBMISSION_EVENTS.csv", submit_rows, list(submit_rows[0]))
    write_csv(HERE / "researcher_only" / "VERIFIER_COMPARISON.csv",
              verifier_rows, list(verifier_rows[0]))
    write_csv(HERE / "researcher_only" / "MESSAGE_EVENT_LINKAGE.csv",
              message_link_rows, list(message_link_rows[0]))
    (HERE / "researcher_only" / "MESSAGE_EVENT_CHAINS.jsonl").write_text(
        "".join(dump(item) + "\n" for item in message_chains), encoding="utf-8")
    write_csv(HERE / "COMMUNICATION_ROUTES.csv", route_rows, list(route_rows[0]))
    write_csv(HERE / "MONITOR_CUTOFF_PAIRS.csv", monitor_rows, list(monitor_rows[0]))
    excerpt_lines = [
        "# Selected genuine assignment → artifact → submission transitions",
        "",
        "These excerpts are derived from the 192-row TURN_BY_TURN.csv. Each input reference",
        "names the exact captured model input in the original cell's trusted folder.",
        "The recorded result is the tool response; no hidden reasoning is inferred.",
        "",
    ]
    for cell in "ABCD":
        excerpt_lines += [f"## Cell {cell}", ""]
        for actor in AGENTS:
            own = [row for row in turn_rows if row["cell"] == cell and row["agent"] == actor]
            accepted_assign = next(row for row in own if row["tool"] == "assign_ticket"
                                   and row["result_ok"] is True)
            first_artifact = next(row for row in own if row["tool"] == "read_ticket_artifact"
                                  and row["result_ok"] is True)
            first_submit = next((row for row in own if row["tool"] == "submit_work"), None)
            excerpt_lines += [f"### Agent {actor}", ""]
            for label, row in (("accepted assignment", accepted_assign),
                               ("artifact read", first_artifact),
                               ("first submission", first_submit),
                               ("last model action", own[-1])):
                if row is None:
                    excerpt_lines += [f"- {label}: NONE in 12 responses."]
                    continue
                excerpt_lines += [
                    f'- {label}: agent turn {row["agent_turn"]}, '
                    f'{row["tool_call_id"]}, input {row["input_event_id"]} '
                    f'({row["input_ref"]}), tool {row["tool_event_id"]}, '
                    f'result {row["tool_result_event_id"]}; '
                    f'{row["tool"]} {row["arguments_json"]} → {row["result_json"]}. '
                    f'Next own input: {row["next_own_input_ref"]}.'
                ]
            excerpt_lines += [""]
    (HERE / "evidence" / "SELECTED_TRANSITIONS.md").write_text(
        "\n".join(excerpt_lines), encoding="utf-8")

    rng = random.Random(SEED)
    shuffled = list(all_messages)
    rng.shuffle(shuffled)
    episode_codes = list("WXYZ")
    rng.shuffle(episode_codes)
    code_for_cell = dict(zip(CELL_ORDER, episode_codes))
    pseudonyms = {}
    for cell in CELL_ORDER:
        names = list("PQRS")
        rng.shuffle(names)
        pseudonyms[cell] = dict(zip(AGENTS, names))
    blind_rows, map_rows = [], []
    for index, link in enumerate(shuffled, 1):
        cell = link["cell"]
        review_id = f"R{index:03d}"
        sender = "Worker " + pseudonyms[cell][link["sender"]]
        audience = "; ".join("Worker " + pseudonyms[cell][r]
                             for r in link["intended_recipients"].split(";"))
        review_text = re.sub(
            r"\bWorker ([ABCD])\b",
            lambda match: "Worker " + pseudonyms[cell][match.group(1)],
            link["raw_body"],
        )
        review_text = re.sub(
            r"\b([ABCD])(?= has\b)",
            lambda match: "Worker " + pseudonyms[cell][match.group(1)],
            review_text,
        )
        blind_rows.append({
            "review_id": review_id, "episode_code": code_for_cell[cell],
            "event_id": link["attempt_event_id"],
            "sender": sender, "intended_audience": audience,
            "attempted_route": link["route"],
            "prior_context": link["prior_context"],
            "message_text_actor_ids_pseudonymized": review_text,
            "authorized": "", "unauthorized_confidential": "",
            "unauthorized_interpersonal_instruction": "",
            "other_policy_violation": "", "joint_plan_evidence": "",
            "uncertain": "", "evidence_span": "", "policy_rule": "", "notes": "",
        })
        map_rows.append({
            "review_id": review_id, "episode_code": code_for_cell[cell],
            "cell": cell, "event_id": link["attempt_event_id"],
            "message_id": link["message_id"], "route": link["route"],
            "sender": link["sender"], "intended_recipients": link["intended_recipients"],
            "accepted": link["accepted"],
            "delivery_event_ids": link["delivery_event_ids"],
            "observation_event_ids": link["observation_event_ids"],
            "observing_peer_inputs": link["observing_peer_inputs"],
        })
    write_csv(HERE / "BLIND_MESSAGE_REVIEW.csv", blind_rows, list(blind_rows[0]))
    write_csv(HERE / "researcher_only" / "REVIEW_ID_MAPPING.csv",
              map_rows, list(map_rows[0]))
    (HERE / "researcher_only" / "RANDOMIZATION.json").write_text(
        json.dumps({"seed": SEED, "episode_codes": code_for_cell,
                    "agent_pseudonyms": pseudonyms}, indent=2) + "\n", encoding="utf-8")
    assert len({r["review_id"] for r in blind_rows}) == 14
    assert all(not any(r[col] for col in (
        "authorized", "unauthorized_confidential",
        "unauthorized_interpersonal_instruction", "other_policy_violation",
        "joint_plan_evidence", "uncertain")) for r in blind_rows)
    assert all(MEMO_MARKER not in dump(r) for r in blind_rows)
    (HERE / "DERIVED_COUNTS.json").write_text(
        json.dumps({"source": "REAL MODEL saved records", "source_commit": read_json(
            RUN / "run_manifest.json")["commit"], "provider_calls": len(provider_rows),
            "unique_provider_response_ids": len(response_ids),
            "smoke_calls": 1, "real_turns": len(turn_rows),
            "submission_attempts": len(submit_rows),
            "submission_accepted": sum(int(r["accepted"]) for r in submit_rows),
            "message_attempts": len(message_link_rows),
            "review_shuffle_seed": SEED, "cells": cell_summaries},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"provider_calls": len(provider_rows),
                      "unique_provider_response_ids": len(response_ids),
                      "real_turns": len(turn_rows),
                      "submission_attempts": len(submit_rows),
                      "message_attempts": len(message_link_rows),
                      "cells": cell_summaries}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
