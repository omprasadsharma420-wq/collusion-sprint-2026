# Source and evidence index

All paths below are relative to `collective-blind-spot-sim/`. Researcher-only. The captured source commit for the V5 live run is `44d605844a29af34db12db63ec90e094d1683496`; this analysis started at HEAD `20e3da5f1ffb301ca1ea5adf3fe507db2b2dfb6f`. Exact run-file hashes are preserved in `experiments/real_v5_longer_horizon_20261025T164017Z/SOURCE_AND_EVIDENCE_SHA256.json` and in the copied manifest. Do not confuse current checkout hash with live-run source provenance.

| Claim | Source range | Saved evidence |
|---|---|---|
| Common policy, approved routes, memo restriction, reporting duty | `protocol_v3.py:16-22`; only policy sentence 16 is excerpted, not memo text | V5 prompt hashes in `V5_LIVE_DECISION.json` and `OFFLINE_V5_READINESS.json` |
| Artifact/verifier semantics, ticket review and score | `protocol_v3.py:220-320`; `world_v3.py:52-77,217-266,365-380`; `world_v4.py:55-77` | `A/trusted/events_v2.jsonl` canonical trace; `V5_TICKET_CHAINS.json`; `A/VALIDATION.json` |
| Message attempt/write/delivery/read | `world_v3.py:122-166` | `V5_COMMUNICATION_CAUSAL_CHAIN.csv`; trace `e000109–e000170`, `e000187–e000240` |
| Model-output handling and early final | `agent_adapter_v3.py:31-76` | `V5_A_58_TURNS.csv`; model output events |
| Response cap, actor scheduler, stop status | `run_real_modal_v5.py:35,251-312` | `V5_A_58_TURNS.csv`; `V5_OFFLINE_INTEGRITY.json`; saved A status |
| Safe projection allowlist | `audit_projection_v2.py:13-69` | saved `A/auditor/projections/pooled_metadata.jsonl` |
| Frozen R1/R2 and replay | `audit_rules_v3.py:11-77` | saved `A/auditor/verdicts.jsonl`; `AUDITOR_DECISIONS.csv` |
| Scripted benign R1 pattern | `run_mock_v3.py:16-70`; `audit_rules_v3.py:24-45` | `scripted_benign_v3_mock/auditor/verdicts.jsonl`, outcome |

The ZIP includes bounded line-numbered snippets for these ranges and exact saved V5 projection/verdict copies. The original experiment folder remains the authoritative full record, including canonical model inputs/outputs and receipt hashes. The ZIP is for researcher verification only and contains the privileged blinded-row map.
