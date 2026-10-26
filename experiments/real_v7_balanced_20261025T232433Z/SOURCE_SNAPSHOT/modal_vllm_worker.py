"""Private, authenticated Modal RPC to one pinned vLLM server.

Importing this module defines resources only. The GPU starts only inside app.run()
when a caller invokes QwenServer.complete.remote(). No public web endpoint exists.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import urllib.error
import urllib.request

import modal

MODEL_NAME = "Qwen/Qwen3-8B-FP8"
MODEL_REVISION = "220b46e3b2180893580a4454f21f22d3ebb187d3"
VLLM_VERSION = "0.10.2"
PORT = 8000

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.10.2",
        "huggingface_hub[hf_transfer]==0.35.0",
        "flashinfer-python==0.3.1",
        "torch==2.8.0",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache = modal.Volume.from_name("collective-blind-spot-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("collective-blind-spot-vllm-cache", create_if_missing=True)
app = modal.App("collective-blind-spot-qwen3-8b-fp8")


@app.cls(
    image=image,
    gpu="L4",
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    min_containers=0,
    buffer_containers=0,
    max_containers=1,
    scaledown_window=60,
    startup_timeout=660,
    timeout=300,
)
class QwenServer:
    @modal.enter()
    def start(self) -> None:
        import vllm
        self.actual_vllm_version = vllm.__version__
        if self.actual_vllm_version != VLLM_VERSION:
            raise RuntimeError(f"Unexpected vLLM version {self.actual_vllm_version}")
        cmd = [
            "vllm", "serve", MODEL_NAME,
            "--revision", MODEL_REVISION,
            "--served-model-name", MODEL_NAME,
            "--host", "127.0.0.1", "--port", str(PORT),
            "--max-model-len", "16384",
            "--max-num-seqs", "1",
            "--enable-auto-tool-choice",
            "--tool-call-parser", "hermes",
        ]
        self.server_log = open("/tmp/collective_blind_spot_vllm.log", "wb")
        self.process = subprocess.Popen(cmd, stdout=self.server_log, stderr=subprocess.STDOUT,
                                        env={**os.environ, "PYTHONUNBUFFERED": "1"})
        self.log_streamer = threading.Thread(target=self._stream_vllm_log, daemon=True)
        self.log_streamer.start()
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"vLLM exited during startup, code={self.process.returncode}: {self._log_tail()}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(2)
        raise TimeoutError(f"vLLM startup exceeded 600 seconds: {self._log_tail()}")

    def _stream_vllm_log(self) -> None:
        """Mirror startup logs to retained Modal app logs for connection failures."""
        with open(self.server_log.name, "rb") as handle:
            while True:
                line = handle.readline()
                if line:
                    print("[vLLM] " + line.decode("utf-8", errors="replace").rstrip(), flush=True)
                elif self.process.poll() is not None:
                    break
                else:
                    time.sleep(0.5)

    @modal.method()
    def info(self) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=10) as response:
            import json
            listed = json.loads(response.read())
        return {"model": MODEL_NAME, "revision": MODEL_REVISION,
                "vllm_version": self.actual_vllm_version, "models": listed}

    def _log_tail(self) -> str:
        self.server_log.flush()
        with open(self.server_log.name, "rb") as handle:
            handle.seek(max(0, handle.seek(0, 2) - 12000))
            return handle.read().decode("utf-8", errors="replace")

    @modal.method()
    def complete(self, request_bytes: bytes) -> dict:
        """Send exact request bytes to localhost; return exact response bytes and status."""
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/chat/completions",
            data=request_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=270) as response:
                return {"status": response.status, "body": response.read(),
                        "elapsed_seconds": time.monotonic() - started,
                        "model": MODEL_NAME, "revision": MODEL_REVISION,
                        "vllm_version": self.actual_vllm_version}
        except urllib.error.HTTPError as exc:
            return {"status": exc.code, "body": exc.read(),
                    "elapsed_seconds": time.monotonic() - started,
                    "model": MODEL_NAME, "revision": MODEL_REVISION,
                    "vllm_version": self.actual_vllm_version}

    @modal.exit()
    def stop(self) -> None:
        if hasattr(self, "process") and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if hasattr(self, "server_log"):
            self.server_log.close()
