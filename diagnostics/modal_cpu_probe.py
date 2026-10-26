"""One isolated, authenticated CPU-only Modal transport diagnostic.

No model, GPU, research prompt, ticket data, or endpoint is involved.
"""

import modal

app = modal.App("cbs-connection-cpu-probe")


@app.function(cpu=0.25, memory=256, timeout=30, startup_timeout=90,
              min_containers=0, max_containers=1, buffer_containers=0,
              scaledown_window=2)
def ping() -> dict[str, object]:
    return {"ok": True, "message": "authenticated Modal CPU roundtrip"}


@app.local_entrypoint()
def main() -> None:
    result = ping.remote()
    assert result.get("ok") is True
    print(result)
