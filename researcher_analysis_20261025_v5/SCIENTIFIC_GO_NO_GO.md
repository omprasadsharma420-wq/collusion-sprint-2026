# Scientific decision memo — proposed, not executed

Date: 2026-10-25 Nepal. Current evidence: V5 A passes receipt/trace/privacy replay checks but scores 2/4; no accepted T4 HOLD review; only one observed peer message has unreviewed content. V5 B/C/D were stopped by the predeclared pilot gate. V3 and V4 have separate protocols. No intervention or real inference is authorized by this memo.

| Exactly three pathways | Evidence and feasibility | Trade-off / decision requirement |
|---|---|---|
| **1. Repair a proven orchestration or observation bug** | **Not applicable on current evidence.** All 58 receipts and 277 chained events verify; artifact reads entered the relevant next inputs; the one observed peer message has an observation record; scheduler behavior matches source. No specific defect or justified code diff is identified. | Reopen only upon a reproducible missing input, dropped observation, wrong scheduler transition, or invalid hash, with a minimal failing test and predicted correction. Do not interpret unproductive model actions as a software bug. |
| **2. Explicit new V6 feasibility protocol** | Possible future design proposal: change **only one** factor, e.g. a prospective human-facing T3/T4 artifact/value guide while keeping model, tools, treatment switches, task, scheduler, and legitimate-work gate frozen. First test whether one Cell A can legitimately complete the work. No V6 source or calls were made. | Changes the environment and requires researcher approval, new version/hash, new offline controls, explicit budget and stopping rule. Do not retroactively combine V6 with v3–v5 or claim treatment efficacy from feasibility. Estimated engineering and independent review: several hours; model/GPU cost unknown until a separately approved budget is specified. |
| **3. Freeze current data and finish a bounded case study** | **Recommended now.** Evidence supports deterministic instrumentation findings, legitimate-task feasibility failure, exact message observation chain, and a scripted R1 false alarm. Draft and package are ready for independent review. | Cannot estimate unauthorized coalition formation, real monitor recall, or the 2×2 treatment effect. Independent message coding (22 rows) and manuscript review remain required; a human review time estimate is 1–3 hours plus adjudication if disputed. |

## Blocking facts before stronger inference

1. The 22 attempted messages remain unreviewed by an independent annotator. In particular, V5's sole recipient-observed text is `PENDING INDEPENDENT CONTENT REVIEW`.
2. V5 B/C/D were not run; V4 B/C/D were not run. V3 had one real trajectory per cell but 0/4 legitimate completion in every cell, so its comparison lacks the intended task-validity basis.
3. R1/R2 consume allowlisted metadata and cannot classify semantic wrongdoing. The real episodes produced no alerts, which cannot estimate recall without known positives. The scripted valid/invalid/innocent controls establish software behavior only.
4. Causal influence requires controlled counterpart episodes and predeclared estimands; none are present for the single V5 observed message. Avoid calling scripted cooperation spontaneous collusion.
5. Same-folder auditor projection is a logical contract, not OS isolation. Any future privacy claim needs process/file access separation and independent tests.

**Decision requested from researcher:** review and freeze this bounded report now. If later scientific work is desired, approve a separately specified V6 factor, legitimate-completion gate, cost ceiling, and independent content-label plan. This memo does not request or imply an automatic run.
