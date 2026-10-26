# DNS failure diagnosis — original attempt preserved

Date: 2026-10-25, Nepal time. This document is an additive forensic note; the original `STARTUP_FAILURE.md`, manifest, progress log, index, app log, and billing snapshot remain unchanged.

## Original failure and evidence limits

The first causal exception visible in the local terminal traceback was `socket.gaierror: [Errno 11001] getaddrinfo failed` in Windows Python 3.11's `socket.py:974`, called from `asyncio.base_events.py:868` and `:1046` while `grpclib.client.Channel.__connect__` / `_create_connection` (`grpclib/client.py:748`, `:725`) attempted a connection. Modal's `modal/_grpc_client.py:164` called `client._call_unary`; `modal/runner.py:66` was invoking `client._stub.AppHeartbeat`. A later wrapper reported `modal.exception.ConnectionError: [Errno 11001] getaddrinfo failed`. The heartbeat warning appeared at approximately 20:13:54 Nepal time; the run manifest records the final abort at 20:14:00.650810 Nepal time. The full local terminal traceback was displayed in the prior Codex session but was not written into the original run folder; the saved manifest and progress retain the wrapper error only. This diagnosis therefore identifies the call path from the observed traceback, with that preservation limit explicit.

The traceback did **not** print the hostname passed to `getaddrinfo`: **FAILED_HOSTNAME_UNKNOWN**. The installed Modal SDK's default and current configured control-plane hostnames are `api.modal.com` and `api.modal2.com`, but the traceback does not establish which, if either, was the failed lookup. There is no evidence that a model-download host or vLLM itself raised this Windows socket error. The worker's saved app log only shows image build, a Torch warning at 20:12:40, and later stop; vLLM output was redirected to an inaccessible stopped worker's `/tmp` file. The model was never verified ready. No model completion request was made.

## Read-only recovery checks

The same project `.venv` reports Python `3.11.15` and Modal client `1.6.2`. `git log -5 --oneline` begins `ac66143`, `15d3835`, `5bf0f12`; tracked files were clean before this investigation. On the later read-only checks:

- `.\.venv\Scripts\modal.exe app list --json` succeeded and showed original app `ap-Kx38rjjkSnt4o4TzK2A9bT` stopped with zero tasks (stopped 20:15:17 Nepal time).
- `.\.venv\Scripts\modal.exe app logs ap-Kx38rjjkSnt4o4TzK2A9bT --tail 200 --timestamps` succeeded and returned the same build/stop sequence already in `modal_app_logs.txt`; no worker-side DNS exception appeared.
- `Resolve-DnsName modal.com` succeeded with four A records (13.227.249.45, .61, .75, .99) and TTL 58 at the check. `.\.venv\Scripts\python.exe -c "import socket; print(socket.getaddrinfo('modal.com', 443, type=socket.SOCK_STREAM)[:2])"` returned two IPv4 socket addresses. This checks `modal.com`, not the unprinted failed hostname.
- No `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, or `NO_PROXY` environment variable names were present; no `MODAL_SERVER_URL` override was present; the read-only OS query found zero connected VPN entries and zero active VPN-like adapters. Proxy values and credentials were not read or logged.
- Modal's public status page reported all services online at the later check. That does not reconstruct service status or local DNS at the original failure time.

## CPU-only authenticated transport check

The isolated source is `../../diagnostics/modal_cpu_probe.py`. The first `modal run` command exited 1 before a remote task was created because the Windows redirected console could not encode Modal's checkmark (`'charmap' codec can't encode character '\u2713'`). Its app `ap-GpPMz78YPYpi0TvM7nBDCK` had zero tasks and was explicitly stopped. The diagnostic output is `../../diagnostics/CPU_PROBE_OUTPUT.txt`.

With only process-local `PYTHONIOENCODING=utf-8`, the second CLI invocation completed the **one actual CPU round trip**: `{'ok': True, 'message': 'authenticated Modal CPU roundtrip'}`. The non-detached app `ap-7ixLxa5N93kD0jbIbQ3a6d` then stopped normally with zero tasks remaining; output is `../../diagnostics/CPU_PROBE_UTF8_OUTPUT.txt`. This proves authenticated Modal CPU RPC worked at 20:30 Nepal time, not that L4 model loading or the earlier failed hostname is now proven reliable.

The dashboard displayed $79.95 credits remaining at approximately 20:31 Nepal time, before any L4 retry. No dashboard budget/spend settings were changed.

## Classification

The original incident was a **local Windows DNS-resolution failure during a Modal control-plane heartbeat**, with exact failed hostname unknown. It has not reproduced in read-only CLI checks or the successful CPU round trip. The CPU probe's initial console-encoding failure was a separate local output issue and was resolved without changing the research protocol or network settings. No global DNS, proxy, VPN, hosts-file, security, model, GPU, or parser change was made.
