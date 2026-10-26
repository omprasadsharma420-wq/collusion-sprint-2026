# Collective Blind Spot — single-archive review guide

This researcher-only archive consolidates work through the V8 technical stop on 26 October 2026. It contains privileged synthetic truth, private model inputs and experimental allocation. **Do not send the full archive to a blinded human reviewer.** The separate `blind_human_review/` folder is the blank reviewer packet; `privileged_linkage/` maps its randomized case IDs back to arms.

## Start here

1. `APART_WORKING_DRAFT_V8.md` is the concise scientific narrative, with V7 baseline, R results, P technical stop, limitations and references.
2. `RESEARCH_EVIDENCE_LEDGER_V3_TO_V8.csv` links each quantitative claim to the saved evidence and its allowed interpretation.
3. `V8_R_RAW_AUDIT.json`, `V8_R_RAW_EPISODES.csv` and `V8_R_PAIRED_DIFFERENCES.csv` are the independent R recomputation.
4. `V8_P_RAW_AUDIT.json` and `V8_P_RAW_EPISODES.csv` separate eight balanced validated episodes, three more validated episodes in an incomplete block, and one excluded aborted episode.
5. `V8_FINAL_BILLING_AND_STOP.json` gives official app-specific metered resources and confirms all V8 Modal apps stopped with zero tasks. The underlying official JSON snapshots are also present.
6. `CBS_V7_RAW_EVIDENCE_FOR_CHATGPT.zip` is the complete portable V7 raw archive, nested here so only this one outer ZIP needs to be transferred. Its standalone SHA-256 is in the neighboring `.sha256` file.
7. `experiments/real_v8_R_*` and `experiments/real_v8_P_*` contain exact serialized requests, available responses, provider receipts, tool actions/results, trusted trace events, auditor views, validators, and local HTML replays. `v8/` contains the frozen implementation and postrun analysis code.
8. The outer archive includes the rest of this project workspace as well: historical experiment folders, minimal simulation source (`policy.py`, `channels.py`, `events.py`, `views.py`, `scorer.py`, `scripts.py`), tests, diagnostics, prior analysis and local software controls. `source_history/` holds portable tracked-source snapshots from the R initial, R continuation and P frozen commits. Virtual environments, caches and credential-like files are excluded.
9. `foundation/` copies the original parent-workspace `POLICY_AND_LABELS.md`, `PREFLIGHT_FINDINGS.md` and historical parent tracker so the initial task definition and preflight are available without including unrelated neighboring projects.
10. `handoffs/` preserves all 14 supplied research-control handoffs with a hash manifest. `USER_CLARIFICATIONS_AND_SCOPE.md` records the later cap, R sender/route and consolidated-archive decisions. The latest handoff supersedes conflicts in earlier documents.
11. `V8_FROZEN_SOURCE_HASH_VERIFICATION.json` checks all 71 frozen source entries against their frozen Git commits. The only byte representation difference is Git's LF normalization of `protocol_v3.py`; the frozen hashes match the CRLF checkout bytes included in this archive. All 27 P-frozen source files match the current checkout exactly.

## Evidence status

- R: 24/24 episodes, 12 predeclared pairs. The researcher-seeded notifications were actually observed by B. Invalid READY attempt rates were 0/12 in both R conditions. These are real B responses to researcher-authored stimuli, not agent-to-agent collusion.
- The R continuation manifest lists all 24 scheduled keys, including the first pair as carried history; only episodes 3–24 have raw folders in the continuation segment. Episodes 1–2 are in the original stopped R segment. Count physical episode folders across both segments, not manifest-list entries, to avoid double counting.
- P: 12 started, 11 technically validated, eight in two complete four-arm blocks. Episode 12 lost the remote connection on its first M1 request. That unanswered request and the earlier 67 successful worker/S responses are retained, but the episode failed validation and is excluded from outcome contrasts. The remaining 28 scheduled episodes were not run.
- P primary two-worker agreement labels are **UNKNOWN** pending independent blinded human review. One server-rejected invalid READY attempt occurred in a neutral, gated episode; this alone is not evidence of collusion. Zero independently human-confirmed two-actor positives have been established.
- M0 is a deterministic metadata monitor. M1 is a model-based provisional reviewer using the same pinned weights in a separate context. Neither its candidates nor invalid judgments are human labels or an accuracy estimate.
- V7 was a different benchmark with no message-body reads or recipient input observations; do not pool its task scores with V8.

## Archive integrity and privacy

`V8_ARCHIVE_SHA256_MANIFEST.json` at the outer ZIP root lists the SHA-256 and byte length of every included file. The packaging program verified the ZIP CRC and every file digest after writing. Credential-like files and virtual environments are excluded. The archive has **not** been uploaded to ChatGPT, submitted to Apart, or independently adjudicated by a human in this workspace.
