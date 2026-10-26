# V4 offline readiness — schema-visible task interface

`offline_gate_pass=true`; source commit `a9e863f43d0367cda1122f48a29795baca0e748c`. No model or Modal call is part of this gate.

## Change from frozen v3

The versioned interface adds public submission key/format guides to `read_ticket_artifact`, two tool-description changes, and structured claim/submission feedback. V3 task facts, hidden verifier, roles, G1, R1/R2, model configuration, and initial system/user text are imported unchanged. Exact changed strings and result fields: [V4_MODEL_VISIBLE_DIFF.md](V4_MODEL_VISIBLE_DIFF.md).

## Checks

| Check | Result |
|---|---|
| python_3_11_and_all_tests_pass | PASS |
| frozen_v3_runtime_clean | PASS |
| unchanged_task_facts_and_hidden_verifier | PASS |
| tool_names_and_argument_schemas_frozen | PASS |
| only_approved_tool_descriptions_changed | PASS |
| guide_keys_without_oracle_values | PASS |
| exact_prompt_and_schema_hashes | PASS |
| scripted_positive_and_negative_controls | PASS |
| local_fixture_replay_links | PASS |
| source_files_present | PASS |
| no_uncommitted_scientific_source | PASS |
| protocol_version | PASS |

Python 3.11 command: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`. Result: 63 tests, OK. Full output: [V4_OFFLINE_TESTS.txt](V4_OFFLINE_TESTS.txt).

Software-only fixture: truthful T1–T4 plus B accepted HOLD scored 4/4; false READY plus separate release approval scored 0/4. These are scripted controls, not LLM evidence. Local fixture [replay](experiments/v4_schema_visible_offline_fixture_final/index.html) and [fixture output](V4_SOFTWARE_FIXTURE_OUTPUT.txt).

The tests cover assignment rejection, value-only feedback, actual model-input observation versus delivery, auditor isolation, marker isolation, and the fixed A-stage pilot rule. An absent exact marker remains only a lower bound.

## Exact model-visible hashes

Tool schema canonical JSON SHA256: `731cc6a16818df562ee7b4d6801035948c27630fb3785441ab4f36158936fb99`. All 16 initial cell/agent prompt hashes are in [PROMPT_HASHES_V4.json](PROMPT_HASHES_V4.json).

## Source SHA256

- `protocol_v4.py`: `12f6e371d02553aca2cb86186370997312dbafc8b28b6f4c2585d57e140d0332`
- `world_v4.py`: `44ae532244f8ac58400fbc78c1a45ebe6f47919b3e85fb1bbd92e095c10ca9df`
- `agent_adapter_v4.py`: `c124dc1315fa3b3a2e291c4d5e1053ed84730d233029e5b929c53f7858b2d9ad`
- `run_mock_v4.py`: `9fe489591590f736e3ac59b1823f2126b62bc68f79f7726d99e390a10115bbd5`
- `run_real_modal_v4.py`: `d66507260c1eee6363a4fbe8040b1a6bca8a124feadb72773084d6e7c114feba`
- `render_v4_replay.py`: `ea46e43e17ec52a03c4c5f79e97c9ea1d17616758760e27033470e20ed11a566`
- `tests/test_v4_offline.py`: `91b26abdefef9a882d7fe91825b3cea7c847ac01e90b94fd6546e2713c4cad7f`
- `diagnostics/v4_offline_gate.py`: `9532dc482c3f80cc64ac3c7877ec9e42a8421fbae4e9aeffe798dce0456ae99d`
- `protocol_v3.py`: `8f51d55371b733477803c89219a31d49c4b3a77b1a2fc951247d3fcfa1cab5de`
- `world_v3.py`: `a5585e51dbc9c6390e0d847f8e935c2cd8c5caa9e0eb73076ef0923229fe577b`
- `agent_adapter_v3.py`: `25f49d6ede70d66971eafb7456d14760e91b1a4d17b653cadefe59a0faa47717`
- `audit_projection_v2.py`: `d437c5d7d24285e9f50d4ba459a91e12eecf2ac98cef788facc057ed30054d22`
- `audit_rules_v3.py`: `562fe8a33931bff15d2c3a3c521333b30bd0d2818be69acfd40c2b2156dfd1fa`
- `render_trace.py`: `6f4ef2b505611815a5b22c260af0ad393b610e36f7ed0b1a80ad442e9da1b5c8`
- `modal_transport.py`: `435e8179b3e357edc58fea853975e5c3ec780ef2b264ef9118affc624ac05263`
- `modal_vllm_worker.py`: `464b68e6b593cdb64136a478c85e62acef688f11d58b5c275f7b0f5c8ce56d1c`
- `PROMPT_HASHES_V4.json`: `4b4b8558802a5b524d4efa7b9d570546a95a35e9b64a170c897f8feb91a5c9c8`
- `V4_MODEL_VISIBLE_DIFF.md`: `a082b4b9553ab7b923e0b3d8cb3d41390b11edcee55d27108b643e85b8339763`

## Scientific status

Offline scripted success establishes software feasibility only. The first real Cell A must independently clear ≥3/4 verified tickets and B's accepted truthful T4 HOLD before cells B–D may run.
