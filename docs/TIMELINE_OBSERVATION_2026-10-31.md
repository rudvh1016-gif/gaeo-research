# Preserve checked observations in timeline items — local draft

Based on Research #12 at `f410a1da7c16162e4e0df1243f55bd93e2165fe8`.
Private #194 at `cd074d65006b523a09ce3c5e27b8db446187f98d` requires a per-item observation claim. Research's checked filing rows already carry that claim, but `company_timelines` discarded it. The projection now copies the existing `observedAt` value without generating, rounding or replacing it. Missing legacy values remain absent. Invalid direct helper inputs are not repaired; the production `build_all` source loaders still reject missing, invalid or late claims before publication.

This is an additive field in the existing `disclosure-research-public-v1` / existing schema contract, consistent with the filing field added in #12. It does not imply that all historical v1 items have an observation. Consumers must inspect each item and retain legacy UNKNOWN handling. File hashes, sizes and record IDs are calculated from the complete serialized bytes including this field. No new observation-authentication guarantee or coverage guarantee is introduced.

## Local validation

- Windows / Python 3.14: 41 disclosure-builder and title-classification tests passed, excluding the existing committed-output checkout hash test. Four new builder tests cover projection through both source loaders and merge, manifest bytes, subsecond timezone boundaries, missing legacy values, and rejection of unverified timeline source rows.
- Two selected new preservation tests against the unchanged #12 projection fail as expected: two assertion failures, zero errors. The changed projection passes them.
- An external isolated cross-repository harness passed four synthetic tests through actual Research `build_all` bytes, Private #191's manifest adapter, and Private #194's risk/thesis consumer. A filing outside the 21-day filing window retains its independently pending merger signal within the 60-day timeline window. Missing/late item times and item-free legacy summaries remain UNKNOWN without a forced exit even with self-consistent wire hashes. A late source claim blocks the producer.
- Private's isolated #190/#191/#192/#194 combination: 379 related source, risk, finance, candidate, thesis, lookahead, observation, policy and pipeline tests passed. This is local evidence, not merged-head Linux CI.
- Broader Research Windows checks did not pass: 187 tests, six failures and 67 errors. Unchanged #12's original tests in the same environment reproduce six failures and 67 errors across 183 tests. These include the existing checkout byte/hash mismatch and Windows budget/path/date behavior. No existing tests or expectations were weakened. The initial new-test attempt also hit sandbox temporary-directory permissions; using a workspace temporary directory resolved that issue.

The existing frozen source snapshot still blocks with `DISCLOSURE_RECEIPT_CONFLICT` in a read-only build. Source files and existing publication bytes have matching before/after SHA-256 values. No generated publication or source record was backfilled. This patch does not restore the historical observation evidence behind Private's previously reported 87 FAIL-to-UNKNOWN transitions.

## Remaining release gates

Production remains NO-GO. Source-title reconciliation, authenticated observation provenance, immutable history and progress-safe retries, completeness/truncation and negative-window evidence, budget/concurrency/crash recovery, backups, actual decision-time consumed bytes and ledger impact, and natural PAPER evidence remain open. Stored claims are not proof of provider truth or protection against deliberate backdating. No real holdings or original decision ledger was audited.

Only source, synthetic tests and this note are intended for review. No orders, account changes, production ledger, raw records, workers, schedules, provider requests, service AI calls, new paid resources, main merge or production deployment were performed. A remote draft branch creation was denied by automatic approval review, which classified the task as unrelated SEO/site work. No workaround was used. The user subsequently explicitly authorized this Research branch and draft PR, and the single authorized branch-creation retry succeeded. Publication and exact-head CI status are recorded in the draft PR; no merge or deployment is authorized for this unready change.
