# Correlated-family audit with recurring overlapping supports

The active-group implementation reuses membership indexes after bindings retire.
The earlier exhaustive domain has at most one alias and one request, so it
cannot exercise interactions between overlapping support sets. This audit
checks those interactions against a separate finite-table specification.

## Domain

The reference has four states, four requests (`ab`, `bc`, `ca`, `tick`) and
three binary role aliases (`x`, `y`, `z`). `tick` advances a saturating counter.
A probe stutters. Probe `ab` requires both of its referenced roles from phase
one, `bc` from phase two, and `ca` from phase three. At phase zero, all probes
allow. The policy encoding retains the three pairwise support sets in each
phase, so the same support projection can pass before a state change and fail
after it. A cached membership partition remains useful; a cached earlier
verdict does not.

Every nonempty subset of the eight joint bindings is supplied as an explicit
family: `2^8 - 1 = 255` families. Of these, 228 families are not Cartesian products of their coordinate
projections; the other 27 are Cartesian subfamilies. Completing one of the
228 correlated families independently introduces excluded bindings. The 65 target tables are
the baseline and every single-cell decision or successor change. There are
16 cells, one alternative decision, and three alternative successors at each
cell: `1 + 16 * (1 + 3) = 65`. Each changed table differs in exactly one cell;
simultaneous decision-and-successor changes are outside this domain.

The cross product contains 16,575 family diagnoses. There are 520 distinct
target/binding pairs. Their independent answers are reused across explicit
families, giving 66,560 checked binding rows; those rows are not 66,560
independent source programs or applications.

## Independent comparison

`source_cell` specifies the source transition table directly, without
interpreting the policy AST. `oracle_profile` searches explicit source/target
pairs and reconstructs every replay from the two initial states. Neither uses
production policy stepping, support discovery, target traversal, or family
normalization. The audit compares the full per-binding rows, selected shortest
words, every replay field, and all semantic aggregate fields. Five focused
controls additionally compare all 128 source-table cells with the policy
encoding, check the domain, exercise delayed retirement and a correlated
family, reject an altered replay binding, and execute three faulty variants
of the implementation.

The baseline constructs all four support indexes (the three pairwise sets
and the empty support) before retirement. It creates 32 memberships and
removes 28 as seven bindings fail. Since each of eight bindings can enter each
index at most once, 32 created memberships establish that all four indexes
were built before retirement. The 16 support queries include 12 queries of
existing indexes. One binding matches; six have shortest
length two and one has shortest length three. This exercises later uses of
indexes from which active members have already been removed.

## Results

The authoritative run is
`results/support-overlap/`.
All 16,575 family diagnoses agree, including 66,560 binding rows and 127,744
witness replay rows. Family outcomes are 1 all-matching, 127 partly matching,
and 16,447 without a matching member. Binding rows have shortest lengths
one (16,384), two (40,960), three (6,912), four (2,176), or match (128).
The strong concentration of failing outcomes follows from the perturbation
domain and is not a prevalence estimate.

| Executed faulty variant | Independent expectation | Faulty result | Detected |
| --- | --- | --- | --- |
| Reuse an earlier probe decision for the same support projection | 1 matching binding | 8 matching bindings | Yes |
| Omit the overlapping support coordinate `y` | 1 matching binding | 2 matching bindings | Yes |
| Cartesian-complete the explicit family `{(r,r,r),(s,s,s)}` | 2 supplied bindings | 8 returned bindings | Yes |

All three variants return a result; rejection occurs in the independent
comparison, rather than only in an implementation assertion. The full inputs,
compressed complete profiles and execution receipt are retained.
`results/support-overlap/coverage.json` derives coverage from those retained records:
13,515 diagnoses build all four indexes, 13,514 also remove members, and
14,820 diagnoses use a genuinely non-Cartesian supplied family.

## Reproduce

From `artifact/`, choose an unused output directory:

```sh
python3 -B -W error proofs/audit_support_overlap.py --output /tmp/authrefine-overlap-audit
python3 -B -W error -m unittest discover -s tests -p test_support_overlap_audit.py -v
```

The runner needs only the Python standard library and refuses an existing
output directory. The recorded focused test run passes all five methods with
no skips. The audit is a finite implementation check and supplies no timing
comparison or mechanical proof of the Python program.
