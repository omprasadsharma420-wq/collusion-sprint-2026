# Collective Blind Spot

Public research workspace for a **synthetic** multi-agent release-team study. This repository preserves the toy simulation, versioned experiments, exact model I/O and provider receipts, trusted traces, scorer and auditor views, source freezes, tests, stopped-run diagnostics, and researcher analyses through V8 (26 October 2026).

## Read the evidence before interpreting outcomes

- [Review guide](researcher_analysis_20261026_v8/README_REVIEW_FIRST.md) explains the archive and the evidence boundaries.
- [Working research draft](researcher_analysis_20261026_v8/APART_WORKING_DRAFT_V8.md) separates V7, the R seeded-exposure phase, and the P four-arm phase.
- [Evidence ledger](researcher_analysis_20261026_v8/RESEARCH_EVIDENCE_LEDGER_V3_TO_V8.csv) links numerical claims to raw records and permitted wording.
- [Full evidence ZIP](researcher_analysis_20261026_v8/CBS_V8_RESEARCHER_FULL_EVIDENCE.zip) is a portable copy of the research workspace, with a SHA-256 manifest inside. SHA-256: `51929a19e37861e9a07a9c74f17b41dc71b7344a2e5e6984d39c2aac33ed3232`.
- [Exact submitted paper](submitted_paper/revised%20submission%20pdf.pdf), *Evidence Before Attribution: Outcome–Process Divergence and Auditor Misreads in a Synthetic Multi-Agent Workflow*, is copied byte-for-byte from the researcher-provided PDF. Its SHA-256 is `311777081a243068c1c17d64b27f544c64fc8a7aa21fce892a473b021fcda10e`.
- [Original preflight and measurement policy](researcher_analysis_20261026_v8/foundation/) and [all supplied handoffs](researcher_analysis_20261026_v8/handoffs/) are preserved. The last handoff supersedes conflicts in the earlier ones.

## Current evidence status

R completed 24 real B-only episodes in 12 prescheduled pairs, with researcher-authored notifications observed in B's actual inputs. Invalid READY attempts were 0/12 in both message conditions. The seeded message is not model-authored collusion.

P started 12 of 40 prescheduled episodes. Eleven passed validation; eight form two complete four-arm blocks. A remote connection failure left episode 12 aborted at its first M1 request, and the remaining 28 episodes were not launched. One invalid READY attempt in a neutral gated episode was server-rejected. **No P two-worker agreement is independently human-confirmed; semantic primary labels remain unknown.** M1 judgments are provisional model outputs, not human ground truth. Do not infer detector accuracy or natural collusion prevalence from these records.

The full repository includes `privileged_linkage/`, private synthetic instructions, and oracle evidence. **That linkage is now public.** A human reviewer using the blank packet must be kept unaware of the public linkage until labels are locked; a reviewer who consults this repository cannot be called blinded.

## Offline verification

Use Python 3.11 from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s v8/tests -v
```

The saved postrun logs record 114/114 historical and 15/15 V8 tests passing. These commands make no paid model calls. Historical real-model runs used a pinned private Modal L4 worker; all V8 apps were verified stopped with zero tasks. No external target systems were used.

A fresh check in this public repository clone also passed [114 historical tests](publication_checks/offline_tests_historical.txt) and [15 V8 tests](publication_checks/offline_tests_v8.txt). The repository stages raw source and evidence with Git text normalization disabled; a precommit audit found zero byte mismatches across 14,091 staged files.

The researcher reports that the paper above has already been submitted to the sprint. The PDF is preserved unchanged; this repository update does not revise the submission or imply acceptance or peer review. The original simulator README is preserved as [README_ORIGINAL_SIMULATION.md](README_ORIGINAL_SIMULATION.md).
