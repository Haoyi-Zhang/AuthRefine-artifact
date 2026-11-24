# Fixed bindings under a caller protocol

`src/protocol_profile.py` makes the existing caller-protocol characterization
available to a complete family of fixed interpretations. It does not weaken
the state-observation premise or infer the admissible caller language.

## Result and assumptions

Fix a finite deterministic reference contract, a nonempty finite family `F`
of legal bindings, a finite target `M`, and a finite deterministic partial
caller protocol `A`. The protocol is independent of the binding. At every
target state, the observation specifies every declared contract-state bit.
Let `R_A` be the target/caller pairs reachable from their initial pair through
protocol-enabled transitions. Every enabled target edge on this graph must
be supplied. The executable implementation admits at most 16 caller states,
the same envelope as `verify_protocol`.

For each fixed binding `beta`, define a bad cell `(q,t,x)` by

```
F_beta(nu(q), x) != (target_decision(q,x), nu(target_next(q,x)))
```

where the caller transition on `x` is enabled at `t`. If the initial
observations agree, the binding matches on every admitted word exactly when
no reachable enabled cell is bad. Otherwise, let `(q,t,x)` be a bad cell of
minimum target/caller distance. A shortest path to `(q,t)` followed by `x`
is a shortest admitted distinguishing word for that binding, and its length
is at most `|R_A|`. Initial disagreement has the empty witness.

This is the fixed-binding caller-protocol proposition applied separately to
each member of `F`. The reachability graph is common because its edges depend
only on the target and caller, not on `beta`. Before the first bad layer,
every admitted prefix preserves `source_state = nu(target_state)` for that
binding. This invariant justifies evaluating a reference transition at the
reported target state and then replaying the selected word from the actual
source initializer. The binding does not change during this induction or
replay. A simple shortest path to the bad cell gives the finite bound.

The generic local characterization, shortest-witness argument, and finite
reachable-cover bound are mechanized in `proofs/ProtocolDiagnosis.lean`.
Family enumeration and the Python implementation are validated separately;
this document does not claim that the Python program has been mechanically
verified.

The result applies to an explicit correlated family as well as a Cartesian
declaration: the implementation checks exactly the supplied members. It does
not add their Cartesian completion. This routine enumerates complete
bindings and makes no local-support or symbolic complexity claim.

## API and accounting

```python
from protocol_profile import protocol_binding_profile

result = protocol_binding_profile(
    policy, machine, protocol,
    family=None,                 # or an explicit nonempty iterable
    budget=2_000_000,
    family_limit=65_536,
)
```

The input shapes are the existing policy and target schemas plus the caller
schema from `protocol_check.py`. Target cells may be `None` only if every
reachable caller occurrence of that cell disables the request.

`matching_family` contains the bindings that match every admitted word.
`profiles` contains a matching result or a shortest witness for each binding.
A witness retains request indices, caller states, target states, source
states, decisions, post-state observations, and the same complete binding
on each replay row. `classification` is `all`, `some`, or `none`; `accepted`
means all members match, not merely that at least one does.

The following counters use distinct units:

| Counter | Meaning |
| --- | --- |
| `graph_traversals` | One shared target/caller traversal, or zero for initial disagreement |
| `graph_cells_inspected` | All requests inspected at reachable target/caller pairs, including disabled requests |
| `graph_enabled_edges` | Supplied, protocol-enabled reachable cells |
| `transition_evaluations` | Reference transition evaluations during per-binding diagnosis |
| `replay_evaluations` | Reference transition evaluations while reconstructing witnesses |
| `work_breakdown.family_members` | Input family entries consumed, including duplicates before deduplication |

Ignoring bounded input validation, the graph phase inspects
`|R_A| * |X|` cells once. Full classification evaluates at most
`|F| * |E_A|` reference cells, stopping a binding at its first disagreement.
Witness replay evaluates the sum of returned witness lengths. These are
operation counts, not a predicted running time; reference transitions may
contain different numbers of rules and guard atoms. Complete-family output
still has at least one row per distinct binding.

## Admission and failure order

Complete classification requires a complete target on the admitted graph.
The routine therefore performs graph admission before per-binding semantic
diagnosis. A missing enabled edge raises `Rejected(kind="inconclusive")`
with a shortest admitted path to that missing edge. That path explains an
incomplete interface; it is not a semantic counterexample. A previously
possible short semantic failure does not turn this partial input into a
complete-family result. No partial matching family is returned.

This order deliberately differs from the older `verify_protocol`, which
interleaves fixed-binding comparison and graph traversal and can report an
early semantic mismatch before it would encounter a later missing edge.
The two routines agree on semantic results for fully admitted interfaces;
they need not return the same first outcome for incomplete inputs.

With equal initial observations, a caller admitting no nonempty word remains
inconclusive under the existing executable admission rule. Mathematically
its epsilon-only language is equivalent. An initial disagreement is already
a decisive empty-word witness and is returned before either of these
nonempty-event admission checks. Exhausted work or family envelopes are also
inconclusive, never matches.

## Independent audit

Run from `artifact/`:

```bash
python3 -B proofs/protocol_family_audit.py --output /new/output/directory
python3 -B -W error -m unittest discover -s tests -p test_protocol_profile.py -v
```

The audit enumerates all ordered pairs of nine one-request, two-state,
denial-stuttering reference tables; all 25 partial two-state target tables;
and all nine partial two-state callers. Both bindings and both machines
start at state zero. The 18,225 instances are the exact cross product of this
declared small domain, not an application sample. Table lookup on request
words through length four independently checks admission, every matching
binding, every shortest length, and every returned replay field. The oracle
does not call the implementation's policy evaluator or graph traversal.

The retained run has 600 all-matching families, 2,580 partly matching
families, 5,730 families without a match, 6,075 inactive caller instances,
and 3,240 instances with an absent enabled target edge. Across the 8,910
classified families, 3,780 binding results match, 13,230 first differ at one
request, and 810 first differ at two requests. Two-event tests separately
exercise caller phases, carried policy state, a length-three admitted
witness, explicit correlated families, and rejection order. They do not
expand the exhaustive audit's one-request domain.

`domains.json` records the enumerated tables; `cases.jsonl.gz` gives each
ordered combination and its result; `summary.json` records counts, source
hashes, and the digest of the uncompressed case stream. Mutation tests make
the implementation's reference evaluator return an erroneous value and
corrupt a replay's caller state. The independent oracle rejects both.
