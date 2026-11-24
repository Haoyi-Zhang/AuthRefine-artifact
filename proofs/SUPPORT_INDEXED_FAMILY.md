# Complete family diagnosis through active support groups

`src/family_diagnosis.py` implements `support_indexed_profile`. The procedure
combines the existing local-support lemma with binding-wise shortest-failure
diagnosis. It preserves the full matching family and a shortest replay for
every excluded binding; it does not replace complete classification with a
single uniform verdict.

## Why a representative suffices

Consider a target cell `(q,x)` with observed reference state `s = nu(q)`.
The existing support lemma states that two legal bindings agreeing on
`D_P(s,x)` produce exactly the same decision and successor reference state
at this cell. Partition the currently active bindings by their values on
that support. Evaluating one actual member of each group therefore determines
the cell result for every member of that group. For a restricted family, the
representative is a member of that family; no independent completion of
correlated coordinates is used.

Process target cells in the same breadth-first state order and input order
as `extensions.binding_profile`. Initially every supplied binding is active.
At a cell, retire precisely the groups whose reference result differs from
the target decision or post-state. Keep a separate result and replay for
each member of a retired group.

**Invariant.** Before processing a cell, the active set consists exactly of
the bindings whose equations pass at every earlier cell in this order.

The invariant holds initially. Within a support group all cell results are
equal by the support lemma, so retaining or retiring the whole group preserves
it. A retired binding is not reconsidered later and can never be changed
into a different interpretation by a later group representative.

For a binding first retired at a cell of target distance `d`, every cell at
distance below `d` has passed for that binding. Prefix reconstruction, applied
to that one binding, makes a shortest target path to the cell agree from the
reference initializer. The final request differs, and no word of length at
most `d` can differ. The returned word is consequently a shortest failure,
with the usual bound by the reachable target-state count. Each member receives
its own replay with its own complete binding fixed at every step. A binding
left active after the final cell matches on all request words.

The algorithm therefore returns exactly the same semantic profile as the
binding-outer implementation, including its deterministic witness tie-break:
both select the same first bad cell for each binding and the same stored
shortest target path. Initial observation disagreement gives the same empty
witness for every binding.

This derivation uses the already established support and prefix-reconstruction
results. It is not a new result about partial observations, nondeterministic
targets, concurrency, or inferred business intent. The Python implementation
has not been mechanically verified.

## Cached indexes and retirement

An index is keyed by a support tuple. Each of its groups contains active
binding identifiers with one common support projection. The index is created
from the active family the first time that support is queried. Whenever a
binding retires, the implementation removes it from every existing index,
deleting groups that become empty.

Consequently, every existing index continues to partition exactly the active
family. Later cells with that support visit only nonempty groups. They do not
rescan all family members or rebuild the same projections at every target
state. This maintenance has a cost: retiring a binding updates every index
created so far. The counters include these removals and their coordinate
lookups.

## Cost and limits

Let `N` be the number of distinct supplied bindings and `E` the number of
reachable target cells. At a processed cell `c`, let `A_c` be the active
family and `D_c` its support. The number of reference transitions evaluated
for diagnosis is exactly

```
sum over processed c of | { beta restricted to D_c : beta in A_c } |.
```

This is at most `N * E`, but need not be much smaller. A full-width support
can distinguish every remaining binding. A singleton family also offers no
sharing, and index construction and support scans can add overhead.

With `K` distinct support tuples encountered, each binding is inserted into
at most `K` indexes and removed from each at most once. The sum of projection
coordinate reads is bounded by twice `N` times the sum of the sizes of these
support tuples. These are bounds on index maintenance; reference evaluation,
support computation, graph construction, witness replay, and serialization
remain additional costs. The implementation returns one row per binding and
repeats the complete fixed binding in every witness replay row. Neither
output size nor complete-family setup becomes independent of `N`.

For the existing width fixture with eight binary aliases, all 256 bindings
match. Binding-wise evaluation makes 4,096 reference calls; grouped diagnosis
makes 32. The latter also constructs 2,048 membership projections, reads
2,048 projected coordinates, stores 2,048 index memberships, and emits 256
result rows. The reduction in reference calls is therefore not a claim of
a 128-fold wall-time improvement. Matched measured comparisons must include
these costs and all replay/output work.

## API and retained counters

```python
from family_diagnosis import support_indexed_profile

result = support_indexed_profile(
    policy, machine, family=None,
    budget=2_000_000, family_limit=65_536,
)
```

Inputs, validation, explicit-family deduplication, semantic result fields,
and witness-row format match `extensions.binding_profile`. The target table
is total. The module `protocol_grouped.py` applies active grouping to partial targets
under an explicit caller protocol. `protocol_profile.py` retains the ungrouped
caller comparator; see [PROTOCOL_GROUPING.md](PROTOCOL_GROUPING.md).

| Counter | Counted work |
| --- | --- |
| `transition_evaluations` | Reference calls for legal group representatives |
| `replay_evaluations` | Reference calls in complete per-binding witness replays |
| `support_queries` | Processed cells at which syntactic support is computed |
| `family_projection_evaluations` | Projection tuples computed during index construction and retirement |
| `family_projection_coordinates` | Alias coordinates read for those projection tuples |
| `index_memberships_created` / `removed` | Insertions and removals in cached support groups |
| `active_group_visits` | Nonempty groups visited for representative evaluation |
| `peak_cached_memberships` | Maximum simultaneously retained binding memberships over all indexes |
| `peak_active_groups` | Maximum simultaneously nonempty groups over all indexes |

`work_breakdown` separately charges family ingestion, target edges, support
queries and scanned guard atoms, projections and coordinate reads, membership
updates, group visits, reference calls, replay calls, and result rows. Its
sum is a declared abstract work envelope, not a hardware instruction count.
Bounded schema validation is outside the envelope. Exhaustion raises an
inconclusive result instead of returning an incomplete matching family.

## Verification

The focused tests compare entire profile structures with the existing
implementation and check each shortest witness using the separate direct
source semantics in `exhaustive_audit.py`. They include generated policies
with target-decision mutations, carried-state chains, correlated families,
empty support, full-width overapproximate support, successive retirement
from multiple cached indexes, initial discrepancies, and exact work-cap
boundaries. A deliberately omitted support coordinate falsely merges
behaviorally different bindings; the independent comparison detects all
seven wrongly retained members of that control family.

Run from `artifact/`:

```bash
python3 -B -W error -m unittest discover -s tests -p test_family_diagnosis.py -v
```

The tests establish implementation agreement on their specified cases.
The matched benchmark and larger diagnostic cohorts provide separate
evidence; their sample counts must not be replaced by the number of unit-test
methods or by the number of cached membership operations.

The separate [overlapping-support audit](SUPPORT_OVERLAP_AUDIT.md) exercises
indexes built before retirement and reused after it, and every nonempty
correlated subfamily of three binary aliases. A directly specified source
table and explicit product search check the complete profile without reusing
production stepping or support discovery. This domain complements the
one-request, at-most-one-alias exhaustive audit; its family-context rows
are reported separately from its 520 distinct target/binding pairs.
