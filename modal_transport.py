"""Exact-recording OpenAI-compatible transport for the private Modal worker.

The caller supplies a remote method. This module has no cloud side effects on import.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

MODEL_NAME = "Qwen/Qwen3-8B-FP8"
MODEL_REVISION = "220b46e3b2180893580a4454f21f22d3ebb187d3"
VLLM_VERSION = "0.10.2"
SEED = 4187
MAX_GENERATION_TOKENS = 768


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def build_completion_request(serialized_request: bytes) -> bytes:
    captured = json.loads(serialized_request)
    if set(captured) != {"messages", "tools"} or len(captured["tools"]) != 12:
        raise ValueError("Captured protocol request is incomplete")
    return _json_bytes({
        "model": MODEL_NAME,
        "messages": captured["messages"],
        "tools": captured["tools"],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "temperature": 0,
        "seed": SEED,
        "max_tokens": MAX_GENERATION_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    })


def parse_completion_response(body: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    response = json.loads(body)
    if not isinstance(response, dict) or len(response.get("choices", [])) != 1:
        raise ValueError("Expected one chat completion choice")
    choice = response["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ValueError("Generation truncated at fixed token cap")
    message = choice["message"]
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        if len(tool_calls) != 1 or choice.get("finish_reason") != "tool_calls":
            raise ValueError("Expected exactly one completed tool call")
        call = tool_calls[0]
        if call.get("type") != "function" or not isinstance(call.get("id"), str):
            raise ValueError("Malformed function call")
        function = call.get("function") or {}
        arguments = json.loads(function.get("arguments", ""))
        if not isinstance(arguments, dict) or not isinstance(function.get("name"), str):
            raise ValueError("Malformed function arguments")
        parsed = {"tool_call": {"name": function["name"], "arguments": arguments,
                                "id": call["id"]}}
    else:
        if choice.get("finish_reason") not in {"stop", "eos_token"}:
            raise ValueError("Unexpected finish reason")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Expected final text")
        parsed = {"final": content}
    return parsed, {"usage": response.get("usage"), "finish_reason": choice.get("finish_reason"),
                    "provider_model": response.get("model"), "response_id": response.get("id")}


class ModalTransport:
    """Persists bytes before/after each remote call, including non-200 responses."""

    def __init__(self, remote_complete: Callable[[bytes], dict[str, Any]], root: Path,
                 *, max_calls: int = 195,
                 on_record: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.remote_complete = remote_complete
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.on_record = on_record
        self.call_count = 0
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def respond(self, actor: str, serialized_request: bytes) -> dict[str, Any]:
        if self.call_count >= self.max_calls:
            raise RuntimeError("Absolute model-call cap reached")
        self.call_count += 1
        folder = self.root / f"{self.call_count:04d}_{actor}"
        folder.mkdir(parents=True, exist_ok=False)
        request_bytes = build_completion_request(serialized_request)
        (folder / "request.json").write_bytes(request_bytes)
        record: dict[str, Any] = {
            "actor": actor, "call_number": self.call_count,
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "model": MODEL_NAME, "revision": MODEL_REVISION, "vllm_version": VLLM_VERSION,
            "status": "requested", "response_sha256": None, "usage": None,
        }
        self._write_record(folder, record)
        if self.on_record:
            self.on_record(dict(record))
        try:
            remote = self.remote_complete(request_bytes)
            body = remote["body"]
            if not isinstance(body, bytes):
                raise ValueError("Remote response body must be bytes")
            (folder / "response.json").write_bytes(body)
            record.update(status=remote["status"], response_sha256=hashlib.sha256(body).hexdigest(),
                          elapsed_seconds=remote.get("elapsed_seconds"),
                          worker_model=remote.get("model"),
                          worker_revision=remote.get("revision"),
                          worker_vllm_version=remote.get("vllm_version"))
            self._write_record(folder, record)
            if self.on_record:
                self.on_record(dict(record))
            if remote["status"] != 200:
                raise RuntimeError(f"vLLM returned HTTP {remote['status']}; raw body recorded")
            if (remote.get("model"), remote.get("revision"), remote.get("vllm_version")) != (
                MODEL_NAME, MODEL_REVISION, VLLM_VERSION
            ):
                raise RuntimeError("Worker model/revision/vLLM identity differs from pinned configuration")
            parsed, metadata = parse_completion_response(body)
            if metadata["provider_model"] != MODEL_NAME:
                raise RuntimeError("Provider response model differs from pinned served name")
            record.update(metadata)
            usage = metadata.get("usage") or {}
            for key in self.token_usage:
                self.token_usage[key] += int(usage.get(key, 0))
            self._write_record(folder, record)
            if self.on_record:
                self.on_record(dict(record))
            (folder / "parsed.json").write_bytes(_json_bytes(parsed) + b"\n")
            return parsed
        except BaseException as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            self._write_record(folder, record)
            if self.on_record:
                self.on_record(dict(record))
            raise

    @staticmethod
    def _write_record(folder: Path, record: dict[str, Any]) -> None:
        target = folder / "receipt.json"
        temporary = folder / "receipt.json.tmp"
        temporary.write_bytes(_json_bytes(record) + b"\n")
        temporary.replace(target)
