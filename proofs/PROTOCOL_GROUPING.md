# Active support groups under a caller protocol

`src/protocol_grouped.py` computes a complete fixed-binding profile on the
reachable target/caller graph. It returns the same matching family, selected
shortest words and replay rows as `protocol_profile.protocol_binding_profile`.
The additional mechanism shares each reference transition among active legal
bindings with the same projection onto that cell's support.

## Invariant and shortest witnesses

Before a cell is processed, the active bindings are precisely those that
agree on all preceding cells in breadth-first state order and fixed request
order. Local-support sufficiency gives one common result within each group.
Retiring or retaining a whole group therefore preserves the invariant. Each
retired binding passed every cell at smaller product distance. Replaying the
stored target/caller prefix with that binding reconstructs the observed policy
state; its final request is the first disagreement. No shorter admitted word
can disagree. A shortest path visits no product state twice, so the witness
length is bounded by the reachable target/caller state count.

Caller state determines request admission, not the reference step's support.
Different caller phases can revisit a target observation. The algorithm keeps
their graph positions and replays distinct; it reuses support memberships,
never an earlier verdict just because the support tuple is the same.

## Admission and operational behavior

An initial observation mismatch provides an empty witness for every binding.
With equal initial observations, the graph is fully admitted before grouping:
every reachable enabled target edge must exist, even if an earlier mismatch
would remove every candidate. Missing enabled edges and callers with no
component event return inconclusive. A disabled absent edge imposes no
obligation. Work or family-limit exhaustion returns no partial profile.

Explicit families keep their supplied correlations. Each group representative
is a real member; no Cartesian completion introduces unsupported assignments.
All cached indexes remove a binding when it retires. Graph visits, support
queries, guard scans, projections, memberships, reference evaluations, replay
steps and output rows have separate work counters. Indexing can cost more
than the evaluations it saves, as the native lookup-only experiment shows.

## Independent evidence

Run from `artifact/` into a fresh output directory:

```sh
python3 -B proofs/audit_protocol_grouping.py --output /tmp/authrefine-caller-groups
python3 -B -W error -m unittest discover -s tests -p 'test_protocol_group*.py' -v
```

The audit first checks the existing 18,225 one-request family cases with the
independent direct-word oracle. It then crosses 81 four-state targets, six
callers and all 255 nonempty subfamilies of eight three-alias bindings.
Direct source equations and an independent source/target/caller search agree
on every result in the 123,930-case domain. The retained data are in
`results/protocol-grouping/`. Distinct admitted target/caller/binding answers
number 2,904; the 371,712 binding rows and 572,416 replay rows reuse those
answers across supplied subfamilies. The shortest failures cover lengths 1–7.

Four executed faults are rejected: an omitted support coordinate, a stale
semantic result, erased caller history and classification after a missing
edge has been filled artificially. The stale result is rejected by the
implementation's fixed-binding replay check; independent profile or admission
comparison rejects the other three faulty results. Additional controls corrupt replay fields
without changing the word. These checks complement the proof; they do not
mechanically verify the Python implementation.

## Use

```python
from protocol_grouped import support_indexed_protocol_profile

profile = support_indexed_protocol_profile(policy, target, caller, family)
```

The command-line entry uses `src/profile.py --engine protocol-indexed` and
requires `--protocol`. The ungrouped `--engine protocol` remains available
for comparisons and small-family workloads.
