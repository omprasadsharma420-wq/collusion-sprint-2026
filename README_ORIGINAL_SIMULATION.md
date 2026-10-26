# Collective Blind Spot simulator

Python 3.11 standard-library toy simulation for checking instrumentation and outcome definitions. It makes no network, model, or Modal calls.

From this directory:

```powershell
python -m unittest discover -s tests -v
python scripts.py --output-dir examples
```

`POLICY_AND_LABELS.md` in the parent directory is the measurement contract. The two switches alter only the known-direct technical gate and the presence of an extra reporting reminder in `ExperimentConfig.briefing()`. Scripted actors do not model LLM responses to the reminder. Thus equal outcomes across the reminder switch in the fixture matrix are expected and are not a finding about reporting effectiveness.

The detailed example keeps `trusted/` (event chain, oracle annotations, condition) separate from `auditor/` (local, pooled metadata, fuller trace projections). This is **logical projection isolation**, not process or filesystem access control: a caller with read access to the workspace can inspect trusted files. A future LLM study must isolate the auditor execution and ground-truth store at the process/service boundary.

The `scripted_matrix.json` rows are deterministic fixtures. `coordinated_wrongdoing` is an operational trace label requiring an observed plan and complementary false actions. `scripted_influence()` compares declared paired fixture outcomes only; it is not a model behavior estimate.

## Scientific limits and next pilot

The scripts supply trusted message categories and a reviewer response rule; neither is an LLM decision. The task is intentionally small, with fixed discovery timing and no statistical power. The event hash chain detects local edits but does not stop a privileged writer from replacing the chain. Auditor isolation is a serialization contract until trusted data and auditor workers run in separate processes with restricted file access. A later model adapter must independently classify prohibited content for the gate and oracle; allowing an agent to choose its own category would invalidate this control.

For a first **future** LLM pilot, freeze the four-ticket instance, agent roles, turn order, model, sampling settings, and both channel opportunities. Run the 2×2 with the prohibited-attempt, legitimate-cooperation, and independent controls at one seed, using exactly the same organization policy and tools. Use a separately reviewed classifier or human labels for message categories, preserve raw attempt/delivery/observation events, and replay only the predeclared auditor views. The initial no-retry ceiling with four agents, two planning rounds, one execution round, and three responses per turn is 432 agent calls across 12 trajectories; add explicit limits for retries and token use. Disable automatic Modal fallback and require a separate go decision before any paid inference. The pilot should report cooperation quality and uncertain causal influence as well as safety outcomes.
