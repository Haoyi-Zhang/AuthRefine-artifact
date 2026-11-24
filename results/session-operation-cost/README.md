# Session request-cost evidence

This independent standard-library audit checks the operational theorem in
`proofs/session-operation-cost.md`. The complete initial store, correct supplied
anchors, and full permutation family on unanchored coordinates are explicit.

The retained run covers 124 anchor sets and
2369 anchored binding cases. It checks
1290 transposition certificates with
458854 closed-domain transition comparisons.
The finite BFS checks one uninterrupted word only, at sizes 2, 3, 4.
The general reset/adaptive lower bound follows from the invariant proof;
these finite computations do not enumerate unbounded strategies.

The native record reconciliation uses 30 already
acquired graph edges for 5 constructed words.
There are no new native executions and no new timing benchmark.

From `artifact/`, verify without writing:

```sh
PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
```

To save an independent repetition, use `--output` with a new directory; an
existing destination is rejected before computation. `--native-results` can
select the retained session-correspondence directory. Verification recomputes
all scientific fields, full profile/certificate records, BFS, native-edge
reconciliation, CSV and this README; only the recorded start and elapsed time
are ignored. The native input and retained evidence are never overwritten.

`summary.json` records parameters and counts; `case-counts.csv` has one row per
anchor set; `complete-evidence.json.gz` retains every anchored permutation,
constructed reference trace, one-removal survivor set and transposition
certificate; `bfs.json` records the finite searches; and
`native-edge-reconciliation.json` records the exact existing cells used.
Rows and credentials in JSON labels are one based. Store masks use bit i-1
for row i. A null first difference means agreement on that word.
