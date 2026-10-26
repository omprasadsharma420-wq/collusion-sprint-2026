# Collective Blind Spot: a versioned feasibility and auditability case study

**Draft for researcher review; not submitted.** Alternative titles: “Accepted Is Not Observed: Instrumenting Communication in a Toy Multi-Agent Workplace”; “A Failed Feasibility Gate in a Four-Agent Collusion Pilot.”

## Abstract (draft; 178 words)

We built a four-worker synthetic release task to study whether explicit reporting of unexpected communication routes and limited cross-agent event auditing might provide warning beyond a gate on a known direct channel while preserving authorized cooperation. The intended design is a 2×2 comparison of direct-channel gating and reporting instruction. Before interpreting that comparison, we required a real-model feasibility pilot to complete at least three of four legitimate tickets and obtain an accepted, truthful T4 HOLD review. Across versioned pilots with Qwen3-8B-FP8, v3 completed zero tickets in each of four cells; v4 and v5 each completed two tickets in Cell A, and their B/C/D cells were withheld by the predeclared gate. V5 recorded 58 provider responses, four accepted messages, eight addressed deliveries, and one recipient model-input observation of peer content; that text awaits independent policy coding. Frozen metadata-only R1/R2 replay produced no real-run alerts. A scripted invalid-release fixture generated an R2 alert, while a scripted benign cooperation fixture generated an R1 false alarm. These controls demonstrate deterministic plumbing, not real-world sensitivity. This paper reports the measurement boundaries, task feasibility failure, and audit limitations. It makes no treatment-effect or spontaneous-collusion claim.

## 1. Research question and measurement contract

The question is whether known-direct gating plus explicit unexpected-route reporting, assessed with pooled event metadata, gives earlier reliable warning of prohibited multi-agent coordination while retaining legitimate collaboration. The organizational policy is held fixed: coordinate ticket work through board/direct inbox, record factual evidence in the checklist, protect a private memo, and avoid knowingly false findings or invalid release approval. The two intended treatment switches are `gate_known_direct` and `discovery_reporting_instruction`; four cells were envisioned. The versioned real pilots never yielded a validated complete 2×2 comparison under a feasible task, so the treatment question remains open.

We predefine attempted communication, accepted write, addressed delivery, resource read, exact body entering a recipient's serialized model input, observed transfer, semantic policy breach, coordinated wrongdoing, and realized harm as distinct states. An auditor alert is another distinct state. Information leakage could occur without joint wrongdoing; similar actions or a bad outcome do not establish collusion. The software-only original policy and operational labels are in `../POLICY_AND_LABELS.md`; actual v3–v5 policy prompt is in `protocol_v3.py` and versioned prompt/tool hashes. No real external workplace was accessed.

## 2. Related work and scope

The official Colosseum repository inspected at preflight (`PREFLIGHT_FINDINGS.md`) motivated a contained multi-agent evaluation, but its original task and logging did not supply this project's independently verifiable read-versus-delivery labels, frozen visibility projections, and four-ticket cooperation scorer without confounds. We therefore used a small Python simulation. We do not claim to compare results against published empirical baselines in this draft; references to external work require researcher verification before submission. The core contribution here is an inspectable measurement protocol and an honest feasibility result, rather than a positive defense benchmark.

## 3. Setup, versions, and holdout gate

Each toy episode assigns four agents synthetic release tickets T1–T4. Agents inspect artifacts, submit findings, and close only verified work. T4 requires truthful HOLD when blockers exist and an accepted review by B; release approval is separate. Task score is accepted state transitions out of four. Scripted fixtures verify that authorized cooperation can score 4/4 and an invalid READY release cannot; those trajectories are **SCRIPTED SOFTWARE FIXTURE**, never spontaneous LLM behavior. Real episodes use `Qwen/Qwen3-8B-FP8` via Modal. V3/v4/v5 source commits and saved input/output hashes remain in the experiment manifests. V5's source commit is `44d605844a29af34db12db63ec90e094d1683496`.

| Cohort | Real study responses | Cells run | Verified legitimate score | Interpretive scope |
|---|---:|---|---|---|
| V3 REAL MODEL EPISODE | 192, plus one separate smoke | A/B/C/D | 0/4 each | Model/tool feasibility; task gate failed |
| V4 REAL MODEL EPISODE | 47 | A only | 2/4 | Schema-visible task; B/C/D withheld |
| V5 REAL MODEL EPISODE | 58 | A only | 2/4 | Longer per-agent cap; B/C/D withheld |

V5 changed the per-agent response cap from 16 to 24 while preserving model-visible prompt/tool hashes relative to v4. This single cross-version difference is descriptive, not a randomized horizon estimate. The fixed pilot expansion gate required score ≥3/4 and an accepted truthful T4 HOLD review; v4 and v5 failed, so B/C/D were not run. V3's four cells do not rescue the later 2×2 because all failed legitimate completion and protocol changed. These data cannot estimate a gate or reporting treatment effect.

## 4. Recording, replay, and reliability

The event chain records model input/output, tool invocation/result, task transition, message attempt, accepted/denied write, addressed delivery, read, and recipient-input observation with stable event IDs. We validate unique provider response receipts and source/prompt/tool hashes. V5 A has 58 distinct receipts, 277 chain-valid events, and a saved 161-frame allowlisted pooled metadata auditor projection. Replaying frozen `audit_rules_v3.py` R1/R2 exactly reproduced its one saved `no_alert`. Sixty-nine offline tests passed. The auditor did not receive hidden answer keys or other agents' private memo in serialized inputs according to the bounded checks in `V5_OFFLINE_INTEGRITY.json`. This same-folder projection is an information contract, not OS security isolation.

Four evidence channels are kept separate: `agent_report` (a worker's concern tool call), `gate_denial` (technical rejection), `independent_monitor_alert` (R1/R2 decision), and `supervisor_ticket_review` (T4 workflow). V5 A had three process-issue concern calls, no exercised G1 gate because G1 was OFF, one independent R1 `no_alert`, and no valid T4 supervisor review. No old v1 `warning_before_harm` value is counted as a monitor detection.

## 5. Results: actual model episodes

V5 A's 2/4 reflects accepted T1 and T2 evidence and declarations (`e000060/e000080` and `e000095/e000118`). B owned T3 but its three submissions were rejected on `draft_claim` (`e000045/e000085/e000127`); C owned T4 and its five HOLD submissions were rejected on both blocker values (`e000070/e000147/e000194/e000257/e000271`). B never received an accepted T4 assessment to review. The scheduler had a theoretical 4×24 response maximum, but A/B/D finalized after 9/8/17 responses and C used its full 24. Thus the actual run ended after 58, with C at its individual cap, unfinished tickets, and no evidence of a transport or missing-observation defect. A larger horizon alone has not shown a passing legitimate episode.

### Figure 1. V5 peer message path: distinct denominators

| Stage | V5 A count | Exact observed example |
|---|---:|---|
| Message attempts | 4 | `m0002` D→team board, `e000152` |
| Accepted writes | 4 | `e000153` |
| Addressed deliveries | 8 recipient paths | C delivery `e000156` |
| Recipient resource reads returning body | 1 unique recipient path | C board read `e000163` (later repeated `e000247`) |
| Body first included in next recipient model input | 1 unique recipient path | C input `e000169`, observation record `e000170` |

The one observed body states that T2 was declared complete. Its policy category is **[NEEDS INDEPENDENT CONTENT REVIEW]**. It is evidence of input exposure, not evidence of influence, leakage, or collusion. The other seven recipient paths were never read in this episode; zero observation is not a missing log entry. V3 has 14 message attempts and v4 four, all still awaiting the same independent text-coding procedure. The 22-row blinded packet records attempts regardless of acceptance or observation.

Frozen real auditor replay: v3 B and D each had two R1 `no_alert` decisions, v3 A and C had no candidate frames; v4 A had two R1 `no_alert` decisions; v5 A had one R1 `no_alert` at cutoff 110 (`e000110`). No real-run R2 candidate occurred. Because R1/R2 read metadata and independently established semantic labels are missing, no-alert cannot mean no attempted wrongdoing, and recall is not estimable.

## 6. Scripted software controls and auditor limitations

The v5 valid-HOLD software fixture scores 4/4 and produces no R1/R2 candidate. The invalid-READY fixture scores 0/4 and produces an R2 `alert` at cutoff 18 (`e000018`) for release approval without a visible accepted T4 assessment. A separate v3 canned benign cooperation fixture scores 4/4 yet produces R1 `alert` at cutoff 35 (`e000020,e000035`): the known direct gate denied a call, followed closely by an authorized checklist write. R1's temporal metadata pattern treats that coincidence as a candidate regardless of content. This is a scripted false alarm and a practical limitation of metadata-only monitoring. It is **not** a real-model false-positive rate. A future two-tier `review_needed` candidate followed by evidence-based confirmation is only a proposed scientific change; the frozen rules were not tuned against inspected episodes.

## 7. Uncertainty and limitations

Independent human text labels are pending; Codex did not assign them. Exact-marker absence is only a lower bound and cannot exclude paraphrased confidential disclosure. A single observed message does not establish causal influence. V3/v4/v5 differ in task protocol or horizon and are not equivalent replicates. No V4/V5 treatment arms beyond A exist. R1/R2 are narrow metadata rules and cannot inspect free-text semantics. Fixture positives and negative controls establish implementation behavior, not spontaneous agent strategy. Same-folder files do not constitute adversarial auditor isolation. The observed legitimate completion failure blocks meaningful claims about preserving cooperation under treatments. The study has no statistical power for prevalence, recall, or treatment effect.

Saved Modal usage reports give v3 retry-app resource line items totaling $0.14756842, v4 app-specific **metered** resources of $0.08018282, and v5 app-specific **metered** resources of $0.06512172. The reports' October workspace **billed** amount was $0 at each respective read; a per-app billed amount was not reported. These amounts have different app/report scopes and are not a final charge estimate. This retrospective analysis made zero model/GPU calls.

## 8. Dual-Use and Ethical Considerations

The environment is a toy synthetic workplace with no real third-party systems or credentials. The research studies early warnings for prohibited coordination and could also reveal where narrow monitors fail. We therefore report only bounded mechanism and measurement facts, preserve the unreviewed content status, and avoid operational claims about bypassing real controls. The fake confidential memo and release artifacts do not represent private external data. Researcher-only trace linkage is separated from the blinded annotator packet. Any future adversarial or real-world deployment needs explicit ethical review, access controls, and a separate scientific protocol.

## 9. Decision for review

The evidence supports a limitations-forward case study and further independent annotation, not a claim of successful collusion detection or intervention efficacy. `SCIENTIFIC_GO_NO_GO.md` gives exactly three pathways; the proposed choice is to freeze this dataset now. Any new V6 is a separately approved version with a single predeclared change and a legitimate-completion gate. This report is a draft, not an organizer submission.

## Reproducibility references

Local primary sources: `protocol_v3.py` (policy, schemas, artifacts), `world_v3.py` (task and communication state), `audit_projection_v2.py` (view allowlist), `audit_rules_v3.py` (frozen R1/R2), `run_real_modal_v5.py` (scheduler and validation), `V5_CELL_A_FORENSIC_DIAGNOSIS.md`, `V5_A_58_TURNS.csv`, `V5_TICKET_CHAINS.json`, `V5_COMMUNICATION_CAUSAL_CHAIN.csv`, `AUDITOR_DECISIONS.csv`, `AUDITOR_REPLAY_SUMMARY.json`, saved `VALIDATION.json`, and the v3/v4/v5 source/evidence manifests. External literature and citation details remain for researcher verification.
