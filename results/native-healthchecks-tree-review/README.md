# Independent native-history audit

The standard-library command in proofs/audit_native_healthchecks_tree.py checks
all complete physical SQLite images, admitted histories, raw response values,
independent lifecycle equations, complete branch encodings and individual
production replay rows. It separately verifies executed source-file sets,
exact control patches, module identities and process/collection receipts.

No native application or production checker is imported or executed by this
audit. Native acquisition and fresh replay counts belong to the input study;
this audit adds zero native executions. SQLite images are decompressed into
memory and checked with query_only plus integrity_check. Comparison is JSON
type-sensitive: false, 0 and 0.0 are distinct values.

From artifact/, run:

    python -B proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review
    python -B -OO -W error proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review

The default input is results/native-healthchecks-tree; --results selects a
relocated copy. Default mode is read-only and prints the recomputed summary.
--output writes a new audit directory and rejects existing destinations, input
ancestors, and locations inside protected source/evidence directories.
The input byte contents and modification times must be unchanged after a run.
