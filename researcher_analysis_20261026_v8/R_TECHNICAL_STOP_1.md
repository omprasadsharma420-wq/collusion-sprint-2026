# V8 R technical stop 1 and continuation decision

Original source commit: 5824628e92576e1e5d551785dba3ba4a009becb5.
Original run: experiments/real_v8_R_20261026T062756Z.
The two isolated real smoke responses passed. The first prescheduled matched pair ran: R0 used 2 B + 1 M1 responses; R1 used 12 B + 1 M1 responses. Both original provider outputs and traces remain unmodified. The run stopped after episode 2 because `validate_episode` asserted `len(messages)==1`. The real B had legitimately authored three additional workplace messages. This was a validator-only defect. It was not a model transport or protocol breach.

Read-only revalidation of both saved original episodes under the corrected validator: PASS. The originally saved `VALIDATION.json` for episode 2 remains FALSE as historical evidence. The corrected validator finds one `RESEARCHER_SEEDED_EXPOSURE` message and accepts separately labelled model-authored messages. It verifies all raw B response receipts, captured input/output hashes, exact notification inclusion and frozen M0 replay.

Continuation source commit: 5619b58. Only `v8/run_r.py` and `v8/tests/test_run_r_offline.py` changed from the first freeze. The scientific freeze content, R messages, allocation, prompts, wire settings, M0/M1 views, scoring and P design must compare equal before any resumed call. Resume starts at prescheduled index 3 (block 2), does not repeat the first pair or smoke, and retains both original episodes linked by source segment. No sample size change was made based on observed outcomes.

The app was observed `stopped` with `tasks: 0` before continuation. Modal workspace billing changed from $0.71911164 metered before V8 to $0.80911241 after this first segment; billed cost remained $0 at that snapshot. This is workspace-level metering and must not be mistaken for an app-specific invoice.
