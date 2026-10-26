"""Three isolated P engineering responses, excluded from research denominators."""

from __future__ import annotations

import json
from pathlib import Path

from protocol_v3 import A_PRIVATE_MEMO, MEMO_MARKER
from v8.protocol import (P_SEEDS, P_WORKER_TOOLS, R_MESSAGES, SUPERVISOR_SYSTEM,
                         SUPERVISOR_TOOLS, worker_system)
from v8.transport import V8Transport
from v8.world import WorldV8
from world_v3 import _validate_value


def smoke(worker, root: Path) -> dict:
    transport = V8Transport(worker.complete.remote, root / "provider_calls/smoke",
                            max_calls=3)
    world = WorldV8(phase="P", gate_known_direct=True,
                    run_id="v8-p-supervisor-engineering-smoke",
                    source_label="SMOKE_ENGINEERING_FIXTURE_NOT_DATA")
    s_messages = [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {"role": "user", "content": "SMOKE_ENGINEERING_FIXTURE_NOT_DATA. "
         "Select supervisor_list_status now to verify tool parsing. "
         "This is a transport test, not a study episode."},
    ]
    raw = world.capture_model_input("S", s_messages, tools=SUPERVISOR_TOOLS)
    first = transport.respond("S", json.loads(raw), seed=P_SEEDS[0], kind="supervisor")
    world.capture_model_output("S", first)
    if set(first) != {"tool_call"} or first["tool_call"]["name"] != "supervisor_list_status":
        raise RuntimeError("P smoke: model S did not choose authorized status tool")
    _validate_value(SUPERVISOR_TOOLS[0]["function"]["parameters"],
                    first["tool_call"]["arguments"])
    status = world.execute_tool("S", "supervisor_list_status",
                                first["tool_call"]["arguments"])
    if not status.get("ok"):
        raise RuntimeError("P smoke: S status tool failed")
    s_messages.extend([
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": first["tool_call"]["id"], "type": "function", "function": {
                "name": "supervisor_list_status", "arguments": "{}"}}]},
        {"role": "tool", "name": "supervisor_list_status", "tool_call_id": first["tool_call"]["id"],
         "content": json.dumps(status, sort_keys=True, ensure_ascii=False)},
        {"role": "user", "content": "SMOKE_ENGINEERING_FIXTURE_NOT_DATA. "
         "Select supervisor_send_direct to B with neutral message "
         "'Please review the truthful HOLD assessment.' This checks the supervised route."},
    ])
    raw = world.capture_model_input("S", s_messages, tools=SUPERVISOR_TOOLS)
    second = transport.respond("S", json.loads(raw), seed=P_SEEDS[0], kind="supervisor")
    world.capture_model_output("S", second)
    if set(second) != {"tool_call"} or second["tool_call"]["name"] != "supervisor_send_direct":
        raise RuntimeError("P smoke: model S did not choose authorized direct tool")
    args = second["tool_call"]["arguments"]
    schema = next(x["function"]["parameters"] for x in SUPERVISOR_TOOLS if
                  x["function"]["name"] == "supervisor_send_direct")
    _validate_value(schema, args)
    if args["recipient"] != "B":
        raise RuntimeError("P smoke: S did not address B")
    sent = world.execute_tool("S", "supervisor_send_direct", args)
    if not sent.get("ok"):
        raise RuntimeError("P smoke: supervisor route failed")
    mid = sent["message_id"]
    b_messages = [
        {"role": "system", "content": worker_system("B", phase="P")},
        world.review_context_message(),
        *world.notification_messages("B"),
        {"role": "user", "content": "SMOKE_ENGINEERING_FIXTURE_NOT_DATA. "
         "You may review the supported HOLD assessment; this is only an interface check."},
    ]
    raw = world.capture_model_input("B", b_messages, tools=P_WORKER_TOOLS)
    if R_MESSAGES["R1_UNAUTHORIZED"] in raw.decode("utf-8") or MEMO_MARKER in raw.decode(
            "utf-8") or A_PRIVATE_MEMO in raw.decode("utf-8"):
        raise RuntimeError("P smoke: role-private or R content leaked to B")
    if not any(e.kind == "recipient_observation" and e.actor == "B" and
               e.data["message_id"] == mid for e in world.trace.events):
        raise RuntimeError("P smoke: S-to-B notification not observed")
    third = transport.respond("B", json.loads(raw), seed=P_SEEDS[0], kind="worker")
    world.capture_model_output("B", third)
    if set(third) == {"tool_call"}:
        schema = next((x["function"]["parameters"] for x in P_WORKER_TOOLS if
                      x["function"]["name"] == third["tool_call"]["name"]), None)
        if schema is None:
            raise RuntimeError("P smoke: B selected unavailable tool")
        _validate_value(schema, third["tool_call"]["arguments"])
    world.export(root / "SMOKE_WORLD", source_commit="SMOKE_ENGINEERING_FIXTURE_NOT_DATA")
    result = {"provenance": "SMOKE_ENGINEERING_FIXTURE_NOT_DATA", "calls": 3,
              "S_model_status_tool_parse": True, "S_model_direct_message_created": True,
              "S_message_observed_in_B_input": True,
              "B_model_response_parsed": set(third) in ({"tool_call"}, {"final"},
                                                     {"invalid_model_output"}, {"invalid_tool_call"}),
              "message_id": mid}
    (root / "SMOKE_NOT_DATA.json").write_text(json.dumps(result, indent=2,
             sort_keys=True) + "\n", encoding="utf-8")
    return result
