# Ambiguous budget merge inputs — isolated follow-up

This draft is stacked on Research PR #9 at `0687231947a251d249ab3d9679e6e585d77d44e0`. It must not be merged to main or deployed independently of that unfinished work.

A synthetic input containing `"list":999,"list":0` previously passed through the Git merge driver and produced a count of zero. The merge parser now uses the existing recursive duplicate-key rejecting decoder. Duplicate keys, invalid UTF-8, unreadable inputs and excessive JSON nesting leave the merge unresolved without writing any input. Invalid schema, count types, missing required counters, dates and observation timestamps also cannot be silently treated as absent contributions. Valid legacy unknown counter names retain their numeric contribution in `other`.

The distinction between an absent/empty input and a first-ever ledger remains unchanged and unverified. This patch does not establish protection against concurrent replacement of merge inputs or outputs, distributed reservation safety, immutable observation history, interruption immediately after replacement, subsequent-run quarantine after save failure, midnight/send races or forced runner loss. All those existing NO-GO gates remain open. No actual provider call reduction or production improvement is claimed.

Regression coverage includes each of the three merge positions, nested and escaped duplicate keys, same-value duplicates, malformed JSON/UTF-8/shapes/counts/timestamps, valid independent runner increments, and originals remaining byte-identical on rejection. A POSIX multiprocessing case loads a valid budget in three pending writers, replaces it with an ambiguous original, and requires every writer to refuse saving while preserving that original. The existing normal concurrent-save and Git merge/rebase tests remain in the Linux suite.

Local Windows/Python 3.14 targeted result: 13 tests, OK with 3 POSIX skips. The newly added duplicate-key regression was also run against the unchanged PR #9 baseline and produced the expected 15 subtest failures, zero errors. This confirms that the regression detects the original defect. It is not a passing baseline result.

Validation command:

```text
python -m unittest test_dart_budget_ledger.MergeRejectsAmbiguousOriginals test_dart_budget_ledger.MergeLedgersUnit test_dart_budget_ledger.ConcurrentSavesOnOneMachine
```

Exact-head existing Linux CI is required before this draft can be considered verified. Green CI does not remove the remaining NO-GO gates. Only source, tests and this note change; no stored budget, registry, generated data, production deployment or provider request is part of this patch.
