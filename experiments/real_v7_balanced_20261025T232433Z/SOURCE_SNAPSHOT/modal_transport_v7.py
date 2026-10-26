"""V7 exact-wire transport. Importing has no cloud side effect."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from modal_transport import MODEL_NAME, MODEL_REVISION, VLLM_VERSION

TEMPERATURE = 0.2
MAX_GENERATION_TOKENS = 768
MAX_MODEL_LEN = 16384
BLOCK_SEEDS = {1: 20261026, 2: 20261027}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def completion_request(serialized_request: bytes, *, seed: int) -> bytes:
    captured = json.loads(serialized_request)
    if set(captured) != {"messages", "tools"} or len(captured["tools"]) != 12:
        raise ValueError("Captured V7 request is incomplete")
    return canonical({
        "model": MODEL_NAME, "messages": captured["messages"], "tools": captured["tools"],
        "tool_choice": "auto", "parallel_tool_calls": False,
        "temperature": TEMPERATURE, "seed": seed, "max_tokens": MAX_GENERATION_TOKENS,
        "chat_template_kwargs": {"enable_thinking": False},
    })


def parse_response(body: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    response = json.loads(body)
    if (not isinstance(response, dict) or not isinstance(response.get("id"), str)
            or len(response.get("choices", [])) != 1):
        raise ValueError("Malformed provider response envelope")
    choice = response["choices"][0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("Missing provider message")
    calls = message.get("tool_calls") or []
    finish = choice.get("finish_reason")
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
                                                "raw_arguments": raw_args,
                                                "reason": "model_generated_invalid_json"}}
            else:
                if (call.get("type") != "function" or not isinstance(call.get("id"), str)
                        or not isinstance(function.get("name"), str) or not isinstance(args, dict)
                        or finish != "tool_calls"):
                    parsed = {"invalid_model_output": {"reason": "malformed_tool_call_shape"}}
                else:
                    parsed = {"tool_call": {"name": function["name"], "arguments": args,
                                            "id": call["id"]}}
    elif finish in {"stop", "eos_token"} and isinstance(message.get("content"), str):
        parsed = {"final": message["content"]}
    else:
        parsed = {"invalid_model_output": {"reason": "no_valid_tool_or_final",
                                           "finish_reason": finish}}
    return parsed, {"usage": response.get("usage"), "finish_reason": finish,
                    "provider_model": response.get("model"), "response_id": response["id"]}


class ModalTransportV7:
    def __init__(self, remote_complete: Callable[[bytes], dict[str, Any]], root: Path,
                 *, seed: int, max_calls: int, on_record=None) -> None:
        self.remote_complete = remote_complete
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.max_calls = max_calls
        self.on_record = on_record
        self.call_count = 0
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def respond(self, actor: str, serialized_request: bytes) -> dict[str, Any]:
        if self.call_count >= self.max_calls:
            raise RuntimeError("V7 provider-call cap reached")
        self.call_count += 1
        folder = self.root / f"{self.call_count:04d}_{actor}"
        folder.mkdir(parents=True, exist_ok=False)
        request_bytes = completion_request(serialized_request, seed=self.seed)
        (folder / "request.json").write_bytes(request_bytes)
        receipt: dict[str, Any] = {"actor": actor, "call_number": self.call_count,
                                   "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                                   "model": MODEL_NAME, "revision": MODEL_REVISION,
                                   "vllm_version": VLLM_VERSION, "seed": self.seed,
                                   "temperature": TEMPERATURE, "status": "requested"}
        self._save(folder, receipt)
        try:
            remote = self.remote_complete(request_bytes)
            body = remote["body"]
            if not isinstance(body, bytes):
                raise ValueError("Remote body is not bytes")
            (folder / "response.json").write_bytes(body)
            receipt.update(status=remote["status"], response_sha256=hashlib.sha256(body).hexdigest(),
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
            parsed, metadata = parse_response(body)
            if metadata["provider_model"] != MODEL_NAME:
                raise RuntimeError("Pinned response model mismatch")
            receipt.update(metadata)
            self._save(folder, receipt)
            usage = metadata.get("usage") or {}
            for key in self.token_usage:
                self.token_usage[key] += int(usage.get(key, 0))
            (folder / "parsed.json").write_bytes(canonical(parsed) + b"\n")
            return parsed
        except BaseException as exc:
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            self._save(folder, receipt)
            raise

    def _save(self, folder: Path, receipt: dict[str, Any]) -> None:
        temporary = folder / "receipt.json.tmp"
        temporary.write_bytes(canonical(receipt) + b"\n")
        temporary.replace(folder / "receipt.json")
        if self.on_record:
            self.on_record(dict(receipt))
