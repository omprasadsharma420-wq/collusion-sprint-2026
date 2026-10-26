# Modal startup attempt — no model generation

The bounded run used implementation commit `15d38352988857cd452416a72544633cd2c2ce87` and the pinned `Qwen/Qwen3-8B-FP8` revision `220b46e3b2180893580a4454f21f22d3ebb187d3` on a single Modal L4 app. The vLLM 0.10.2 image built and one worker started. The local Modal client then reported `ConnectionError: [Errno 11001] getaddrinfo failed` during its heartbeat/worker-startup RPC. The worker identity check did not finish.

- App ID: `ap-Kx38rjjkSnt4o4TzK2A9bT`.
- Recorded run wall time before abort: 221.625 seconds. This is not measured GPU occupancy or a billing figure.
- Generated model calls: **0**. Smoke: **not started**. Cells C, A, D, B: **not run**.
- Modal CLI cleanup: `modal app stop --yes ap-Kx38rjjkSnt4o4TzK2A9bT` exited 0. A subsequent `modal app list` reported state `stopped`, with stop time 20:15 Nepal time. The Modal app log ends with `Stopping app - user stopped from CLI` and `Runner terminated`.
- Starting dashboard snapshot before GPU launch: $80.00 credits left, $0.00 October spend, $92.50 workspace usage left. The subsequent official `modal billing summary --for 2026-10 --json` reported October metered cost `$0.05910905` and billed cost `$0E-8`, including `$0.04690632` in ephemeral apps and `$0.00910905` in network egress. This is the whole October workspace summary, not a per-run charge. Ending credit balance was not verified.

Evidence: [run manifest](run_manifest.json), [usage record](usage.json), [official billing summary](modal_billing_summary_after.json), [progress log](progress.jsonl), [Modal app log](modal_app_logs.txt), [stop verification](MODAL_STOP_VERIFICATION.txt), [implementation diff](implementation_diff.patch), and [comparison](comparison.csv). No genuine agent behavior or scientific outcome exists in this attempt.

The authorized instruction says to stop on a concrete blocker. This run was not retried and no substitute model, GPU, provider, or parser was used.
