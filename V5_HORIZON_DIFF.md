# V5-longer-horizon source diff from frozen v4

The only experimental change is the **per-agent maximum model responses: 16 → 24**. This raises one-cell study capacity from 64 to 96 and four-cell capacity from 256 to 384. One optional separate identity smoke remains allowed but is not used by the runner. The 90-minute worker-context cap, 30-minute cell cap, A→B→C→D turn order, A pilot gate, model, provider, seed, parser, data, policy, tools, scoring, and auditor are identical.

Versioned implementation files:

- `protocol_v5.py` re-exports the exact v4 field guides, tool schema, prompt assembly, and hashes; only `PROTOCOL_VERSION` becomes `v5-longer-horizon`.
- `world_v5.py` inherits all `WorldV4` authorization, message, artifact, evidence, and observation logic. Its only override writes the new version label into the researcher manifest after unchanged export.
- `agent_adapter_v5.py` inherits the unchanged v4 agent loop. The v5 runner supplies the response cap 24.
- `run_real_modal_v5.py` is the v4 runner copied with the response budget constants, v5 imports/version/run-folder labels, and researcher-facing filenames updated. The per-cell cap remains 30 minutes, total worker context 90 minutes, and A gate is byte-for-byte the same after v4/v5 naming is normalized. No initial prompt or model-facing tool description changes.
- `run_mock_v5.py` uses the same scripted positive/negative software controls under cap 24 and v5 output labels. `render_v5_replay.py` changes only researcher-view labels/CSS class prefixes.

The [exact runner diff](V5_RUNNER_DIFF.patch) and [prompt hashes](PROMPT_HASHES_V5.json) make this comparison inspectable. The no-cost gate checks that normalizing only the allowed version/cap/path substitutions returns the original v4 runner and fixture code. The v3 and v4 source and run records remain historical and untouched.

This is a prospective horizon intervention, not an unmodified replication. A longer horizon could permit more work or repeat ineffective actions; the software fixture cannot predict genuine model behavior.
