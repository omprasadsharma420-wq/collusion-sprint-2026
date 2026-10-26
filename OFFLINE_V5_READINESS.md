# V5-longer-horizon offline readiness

`offline_gate_pass=true`. Source commit `44d605844a29af34db12db63ec90e094d1683496`. No model or GPU call was made by this gate.

The [v4 causal diagnosis](experiments/real_v4_schema_visible_20261025T160532Z/researcher/V4_CELL_A_CAUSAL_DIAGNOSIS.md) passed the prerequisite integrity gate. The sole prospective treatment is 16→24 maximum responses per agent. Exact [horizon diff](V5_HORIZON_DIFF.md) and [runner patch](V5_RUNNER_DIFF.patch). All initial model-visible prompt and tool bytes match v4 exactly.

| Check | Result |
|---|---|
| v4_stage0_integrity_passed | PASS |
| only_cap_in_runner_after_version_normalization | PASS |
| same_scripted_controls_after_cap_normalization | PASS |
| same_replay_logic_after_version_normalization | PASS |
| bounded_horizon_only | PASS |
| identical_model_visible_prompts_and_tools | PASS |
| task_facts_and_verifier_unchanged | PASS |
| python_3_11_and_69_tests_pass | PASS |
| scripted_controls_4_and_0 | PASS |
| local_fixture_replay_links | PASS |
| source_files_present_and_committed | PASS |

Command: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`. Result: 69 tests, OK; [full log](V5_OFFLINE_TESTS.txt). The scripted [v5 control replay](experiments/v5_longer_horizon_offline_fixture/index.html) scores valid HOLD 4/4 and invalid READY 0/4; it is SOFTWARE FIXTURE only, not model behavior.

Tool schema SHA256: `731cc6a16818df562ee7b4d6801035948c27630fb3785441ab4f36158936fb99`. [All 16 prompt hashes](PROMPT_HASHES_V5.json) are identical to v4.

## Source SHA256

- `protocol_v5.py`: `cfb0bec7ae73bebfa50ec20679ee7a4eeb817cea5fbc95a201d0d9c8454ad438`
- `world_v5.py`: `4e87dcf489aaaf7cab4f7a33638046bf647007ad53bcfaaf60f20f0b18a4eae2`
- `agent_adapter_v5.py`: `2b9153384ee5f25a9f23b9b5d94f4dd4e87d87b4c17c264c05702bec636efd2f`
- `run_real_modal_v5.py`: `6a57f2f3ccb30f4b668e0ba95c86057ae247b670108e8803ac2abe335dce43f4`
- `run_mock_v5.py`: `330208730935356a88d7ac1b8103a2724f76fd8fbe33c05ef72f7051fdd07747`
- `render_v5_replay.py`: `21afdfd8e309a03a5a341b84cf75b721323897f4c86cec1aaa221730b9b32189`
- `tests/test_v5_offline.py`: `c48d7dbfd6ddb6616ca7a35f8316b8a627806a782a5ae9d54c215e69603a338a`
- `diagnostics/v5_offline_gate.py`: `25467e63df6fb56af110b1f4c7d8fa30e921c16745f5c0fa2b4af3c34395a79e`
- `PROMPT_HASHES_V5.json`: `8573a28dc68730a7c526da8370ae6f953224a7d9bea9f458dc582293706d8c37`
- `V5_HORIZON_DIFF.md`: `3f0a1962ec8dbf9656cb7787c920c0f70c342d41ab03e3bd7e913b0c8ecffc3c`
- `V5_RUNNER_DIFF.patch`: `377bfc724ce7b08bd3ddb07492cc0112df26796b4f31e6392c4cef04e9282e02`
- `protocol_v4.py`: `12f6e371d02553aca2cb86186370997312dbafc8b28b6f4c2585d57e140d0332`
- `world_v4.py`: `44ae532244f8ac58400fbc78c1a45ebe6f47919b3e85fb1bbd92e095c10ca9df`
- `agent_adapter_v4.py`: `c124dc1315fa3b3a2e291c4d5e1053ed84730d233029e5b929c53f7858b2d9ad`
- `run_real_modal_v4.py`: `d66507260c1eee6363a4fbe8040b1a6bca8a124feadb72773084d6e7c114feba`
- `run_mock_v4.py`: `9fe489591590f736e3ac59b1823f2126b62bc68f79f7726d99e390a10115bbd5`
- `render_v4_replay.py`: `ea46e43e17ec52a03c4c5f79e97c9ea1d17616758760e27033470e20ed11a566`
- `protocol_v3.py`: `8f51d55371b733477803c89219a31d49c4b3a77b1a2fc951247d3fcfa1cab5de`
- `world_v3.py`: `a5585e51dbc9c6390e0d847f8e935c2cd8c5caa9e0eb73076ef0923229fe577b`
- `agent_adapter_v3.py`: `25f49d6ede70d66971eafb7456d14760e91b1a4d17b653cadefe59a0faa47717`
- `audit_projection_v2.py`: `d437c5d7d24285e9f50d4ba459a91e12eecf2ac98cef788facc057ed30054d22`
- `audit_rules_v3.py`: `562fe8a33931bff15d2c3a3c521333b30bd0d2818be69acfd40c2b2156dfd1fa`
- `modal_transport.py`: `435e8179b3e357edc58fea853975e5c3ec780ef2b264ef9118affc624ac05263`
- `modal_vllm_worker.py`: `464b68e6b593cdb64136a478c85e62acef688f11d58b5c275f7b0f5c8ce56d1c`

If this gate passes, only one fresh real Cell A may start. B/C/D depend on the unchanged ≥3/4 plus accepted truthful T4 HOLD pilot gate.
