# Provenance, verification, and replay

## Source of truth

- Workspace evidence HEAD before this review: `3d98b4102aceb2a65ea535d6e362ca4a2e0afb16`; no tracked edits were present. Frozen live-run source: `d16ec98a46332d9d01836d2f7a4fb451bbb68630`, as recorded in the run and cell manifests.
- Original successful run: `../../run_manifest.json`, `../../smoke.json`, `../../usage.json`, and `../../{cell}/manifest.json`. The prior DNS startup failure is `../../../real_qwen3_8b_modal_20261025T142518Z/` and had **zero** generation calls. Scripted mock fixtures and the isolated smoke are excluded from four real-cell outcomes.
- Model identity in each of 193 successful receipts: `Qwen/Qwen3-8B-FP8` at `220b46e3b2180893580a4454f21f22d3ebb187d3`, vLLM `0.10.2`, Hermes parser. Requests have temperature 0, seed 4187, `enable_thinking=false`, the same 12-tool schema, and a 768 generation-token cap. [PROVIDER_CALLS.csv](PROVIDER_CALLS.csv) lists every unique provider response ID and request/response SHA256; [PROVIDER_COUNTS.csv](PROVIDER_COUNTS.csv) confirms 12 unique calls per cell/agent. The first call is labeled **LIVE SMOKE**, the following 192 **REAL MODEL**.
- All cell prompt hashes were recomputed from the frozen cell configuration and matched each manifest. `git diff --name-only d16ec98 3d98b410 -- protocol_v3.py world_v3.py audit_rules_v3.py PROMPT_HASHES_V3.json agent_adapter_v3.py` yielded no scientific-source changes. The later `render_trace.py` and `run_real_modal.py` diffs were post-run presentation/summary fixes; they did not change canonical events or monitor logic. This forensic package adds derived files only.
- [HASH_MANIFEST.csv](HASH_MANIFEST.csv) records SHA256 and byte length of **current saved worktree bytes** for the scientific source, run manifest, usage, validation, each cell's trace, tool calls, outcome, messages, saved auditor inputs/verdicts, and original replay HTML. [FROZEN_SOURCE_HASHES.csv](FROZEN_SOURCE_HASHES.csv) separately hashes the **actual Git blobs at the frozen run-source commit** and compares them with current worktree bytes and Git content diffs. This distinction matters on Windows: `protocol_v3.py` and `PROMPT_HASHES_V3.json` have checkout line-ending differences but no Git content diff. Representative frozen Git-blob SHA256 values are `protocol_v3.py` `bdca572b3ba13fd2f93f96788b798c11ba9600a5ecbe9f8b2d6362fa76b29c48`, `world_v3.py` `a5585e51dbc9c6390e0d847f8e935c2cd8c5caa9e0eb73076ef0923229fe577b`, `audit_rules_v3.py` `562fe8a33931bff15d2c3a3c521333b30bd0d2818be69acfd40c2b2156dfd1fa`, and `PROMPT_HASHES_V3.json` `1ce463502c53e594d1f85d6a015ebc49771db4cf4dd9ed0b3ff3e3f3fd8612ce`.

## Offline checks actually performed

From `C:\Users\ompra\OneDrive\Documents\New project\collective-blind-spot-sim`:

```powershell
.\.venv\Scripts\python.exe experiments\real_qwen3_8b_modal_20261025T144820Z\researcher\forensic_review\build_tables.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The export script validated **193/193** receipt request/response hashes and **193 distinct** provider response IDs; mapped 192 real calls to their cell/agent input, output, tool invocation and result events; validated each trace hash chain; checked **176/176** available next own inputs contained the preceding tool response; recomputed each cell's prompt hashes, local and pooled projections, and unchanged R1/R2 verdicts; reproduced all 23 submission verifier rejections; and checked the blind packet contains exactly 14 unlabeled real attempts. [BUILD_OUTPUT.txt](BUILD_OUTPUT.txt) and [DERIVED_COUNTS.json](DERIVED_COUNTS.json) capture the derived totals. [OFFLINE_TESTS.txt](OFFLINE_TESTS.txt) records the latest unittest result; the earlier 53-test record remains unchanged in `../../../../diagnostics/RECOVERY_FINAL_TESTS.txt`.

The existing overview's **seven relative links** all resolve. [REPLAY_CHECKS.json](REPLAY_CHECKS.json) verifies each A/B/C/D replay prominently says `REAL MODEL — CAPTURED RUN` and contains captured model inputs/outputs, the collective chronological stream, exact pooled monitor input and verdict panel, and a separate conspicuous `RESEARCHER-ONLY TRUTH — NEVER AGENT/AUDITOR INPUT` section. The HTML is a **local privileged researcher view**; do not publish or feed it to an agent or auditor. It shows visible outputs and tool calls, not inaccessible hidden chain of thought.

Open the original overview locally:

```powershell
Start-Process 'C:\Users\ompra\OneDrive\Documents\New project\collective-blind-spot-sim\experiments\real_qwen3_8b_modal_20261025T144820Z\index.html'
```

The original overview and four replays were **not regenerated or modified in this review**. Browser inventory previously showed the local overview tab title; this review independently parsed the files and all index links. The ZIP contains analysis and selected sanitized excerpts, not a second copy of the privileged HTML.

## Runtime and cost

The read-only authenticated `modal app list --json` check at the timestamp in [CURRENT_MODAL_APP_STATUS.json](CURRENT_MODAL_APP_STATUS.json) shows the original failed L4 app, the two CPU probe apps, and the successful retry app all **stopped with zero tasks**. No deployment or inference was started by this review.

The saved `usage.json` reports 385,701 prompt and 5,756 completion tokens (**391,457 total**) across smoke plus real cells. The official October workspace summary after the pilot was **$0.23910954 metered, $0 billed**. Retry-app resource lines sum to **$0.14756842 metered**, including $0.13689431 L4; a separately billed per-cell/per-call amount is unavailable. Remaining credits after the run were not directly checked. The run manifest gives a 626.234-second retry wall-time upper bound; together with the prior attempt's conservative 221.625-second bound, 847.859 seconds is below the three-hour cap. These are recorded upper bounds, not measured per-agent GPU time.

## Access separation

The `evidence/auditor/` copies contain only the saved sanitized metadata stream and saved verdicts. The `researcher_only/` directory contains treatment linkage, original messages, exposure records, and answer-key comparisons; it is **never** monitor input. The blind CSV and rubric can be shared alone with an independent human annotator. Treat a whole-ZIP upload as a privileged researcher/scientific-partner review, not as an annotation-blind interface.
