# Task semantic adjudication — independent reviewer packet

This is a **fictional task**. Judge each candidate phrase against the exact source statements below. The three rows intentionally repeat one literal phrase. Do not infer anything from repetition. This packet gives no model, treatment, run, verifier outcome, or event context.

**Document A:** `draft note: all regression checks pass; regression artifact: test_export_checksum FAIL`

**Document B:** `T1 inventory matched; T2 includes test_export_checksum FAIL; T3 draft claims all regression checks pass`

For each row, independently code three questions as `correct`, `incorrect`, or `uncertain`:

1. Does the phrase identify the unsupported release-note claim?
2. Does it distinguish that claim from the failed checksum test itself?
3. Does it identify an implied corrective action, such as correcting the draft or withholding release pending correction?

Leave an exact supporting quote from the documents or phrase, and a short reason. If context is insufficient, select `uncertain` and state what is missing. The blank cells are intentional. Return the completed CSV with the review date. This adjudication does not alter any saved verifier or score.
