"""Pinned V8 OpenAI-compatible wire transport; no remote call on import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from v8.protocol import (M1_OUTPUT_SCHEMA, MAX_GENERATION_TOKENS, MODEL_NAME,
                         MODEL_REVISION, TEMPERATURE, VLLM_VERSION)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_m1(value: object, *, cutoff: str, allowed_event_ids: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != set(M1_OUTPUT_SCHEMA["required"]):
        raise ValueError("M1 output field set invalid")
    if value["cutoff_event_id"] != cutoff:
        raise ValueError("M1 cutoff mismatch")
    if not isinstance(value["evidence_event_ids"], list) or any(
        not isinstance(eid, str) or eid not in allowed_event_ids for eid in value["evidence_event_ids"]
    ):
        raise ValueError("M1 cited future or unavailable event")
    if len(set(value["evidence_event_ids"])) != len(value["evidence_event_ids"]):
        raise ValueError("M1 duplicate evidence ID")
    properties = M1_OUTPUT_SCHEMA["properties"]
    for field in ("candidate_label", "suspected_rule", "observation_basis"):
        if value[field] not in properties[field]["enum"]:
            raise ValueError("M1 invalid enum")
    if not isinstance(value["rationale"], str) or len(value["rationale"]) > 400:
        raise ValueError("M1 rationale too long")


def request_bytes(captured: dict[str, Any], *, seed: int, kind: str) -> bytes:
    if kind not in {"worker", "supervisor", "m1"}:
        raise ValueError("Invalid provider role")
    if not isinstance(captured.get("messages"), list):
        raise ValueError("Missing serialized messages")
    body = {"model": MODEL_NAME, "messages": captured["messages"],
            "temperature": TEMPERATURE, "seed": seed,
            "max_tokens": 512 if kind == "m1" else MAX_GENERATION_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False}}
    if kind == "m1":
        if set(captured) != {"messages"}:
            raise ValueError("M1 must not receive actor tools")
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "v8_m1_verdict", "strict": True, "schema": M1_OUTPUT_SCHEMA}}
    else:
        if set(captured) != {"messages", "tools"} or not isinstance(captured["tools"], list):
            raise ValueError("Worker or S tools absent")
        body.update(tools=captured["tools"], tool_choice="auto", parallel_tool_calls=False)
    return canonical(body)


def parse_response(raw: bytes, *, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    response = json.loads(raw)
    if not isinstance(response, dict) or not isinstance(response.get("id"), str) or len(
        response.get("choices", [])) != 1:
        raise ValueError("Provider response envelope invalid")
    choice = response["choices"][0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("Provider message absent")
    finish = choice.get("finish_reason")
    if kind == "m1":
        if message.get("tool_calls") or not isinstance(message.get("content"), str):
            parsed = {"invalid_model_output": {"reason": "M1_non_json_content"}}
        else:
            try:
                parsed = {"m1_json": json.loads(message["content"])}
            except json.JSONDecodeError:
                parsed = {"invalid_model_output": {"reason": "M1_generated_invalid_json",
                                                   "raw_content": message["content"]}}
    else:
        calls = message.get("tool_calls") or []
        if calls:
            if not isinstance(calls, list) or len(calls) != 1:
                parsed = {"invalid_model_output": {"reason": "multiple_or_malformed_tool_calls"}}
            else:
                call = calls[0]
                function = call.get("function") or {}
                raw_args = function.get("arguments")
                try:
                    args = json.loads(raw_args)
                except (TypeError, json.JSONDecodeError):
                    parsed = {"invalid_tool_call": {"name": function.get("name"),
                                                    "raw_arguments": raw_args}}
                else:
                    if call.get("type") != "function" or not isinstance(call.get("id"), str) or not isinstance(
                        function.get("name"), str) or not isinstance(args, dict) or finish != "tool_calls":
                        parsed = {"invalid_model_output": {"reason": "malformed_tool_call_shape"}}
                    else:
                        parsed = {"tool_call": {"name": function["name"], "arguments": args,
                                                "id": call["id"]}}
        elif finish in {"stop", "eos_token"} and isinstance(message.get("content"), str):
            parsed = {"final": message["content"]}
        else:
            parsed = {"invalid_model_output": {"reason": "no_valid_tool_or_final",
                                               "finish_reason": finish}}
    metadata = {"response_id": response["id"], "provider_model": response.get("model"),
                "usage": response.get("usage"), "finish_reason": finish}
    return parsed, metadata


class V8Transport:
    def __init__(self, remote_complete: Callable[[bytes], dict[str, Any]], root: Path,
                 *, max_calls: int) -> None:
        self.remote_complete = remote_complete
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.call_count = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def respond(self, actor: str, captured: dict[str, Any], *, seed: int,
                kind: str) -> dict[str, Any]:
        if self.call_count >= self.max_calls:
            raise RuntimeError("V8 provider call cap reached")
        self.call_count += 1
        folder = self.root / f"{self.call_count:05d}_{actor}"
        folder.mkdir(parents=True, exist_ok=False)
        request = request_bytes(captured, seed=seed, kind=kind)
        (folder / "request.json").write_bytes(request)
        receipt = {"call_number": self.call_count, "actor": actor, "kind": kind,
                   "seed_requested": seed, "temperature": TEMPERATURE,
                   "request_sha256": hashlib.sha256(request).hexdigest(),
                   "model": MODEL_NAME, "revision": MODEL_REVISION,
                   "vllm_version": VLLM_VERSION, "status": "requested"}
        self._save(folder, receipt)
        try:
            remote = self.remote_complete(request)
            body = remote["body"]
            if not isinstance(body, bytes):
                raise ValueError("Remote body is not bytes")
            (folder / "response.json").write_bytes(body)
            receipt.update(status=remote["status"],
                           response_sha256=hashlib.sha256(body).hexdigest(),
                           elapsed_seconds=remote.get("elapsed_seconds"),
                           worker_model=remote.get("model"),
                           worker_revision=remote.get("revision"),
                           worker_vllm_version=remote.get("vllm_version"))
            self._save(folder, receipt)
            if remote["status"] != 200:
                raise RuntimeError(f"vLLM HTTP {remote['status']}; raw response saved")
            if (remote.get("model"), remote.get("revision"), remote.get("vllm_version")) != (
                MODEL_NAME, MODEL_REVISION, VLLM_VERSION):
                raise RuntimeError("Pinned worker identity mismatch")
            parsed, metadata = parse_response(body, kind=kind)
            if metadata["provider_model"] != MODEL_NAME:
                raise RuntimeError("Pinned provider response model mismatch")
            receipt.update(metadata)
            self._save(folder, receipt)
            for key in self.usage:
                self.usage[key] += int((metadata["usage"] or {}).get(key, 0))
            (folder / "parsed.json").write_bytes(canonical(parsed) + b"\n")
            return parsed
        except BaseException as exc:
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            self._save(folder, receipt)
            raise

    @staticmethod
    def _save(folder: Path, receipt: dict[str, Any]) -> None:
        target = folder / "receipt.json"
        temporary = folder / "receipt.json.tmp"
        temporary.write_bytes(canonical(receipt) + b"\n")
        temporary.replace(target)
