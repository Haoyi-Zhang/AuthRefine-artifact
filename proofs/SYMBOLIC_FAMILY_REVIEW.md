# Independent checks of the symbolic family implementation

Run from `artifact/` with an interpreter providing the compiled `dd.cudd`
extension:

```sh
python -B proofs/audit_symbolic_family.py
```

The script requires the actual CUDD extension and prints a structured JSON
result. It does not silently skip that backend or modify any project file.
The completed independent run used Python 3.12.14 and `dd` 0.6.0, exited with
code 0, and returned `status: passed`.

## Inputs and checked obligations

| Obligation | Input and independent check | Observed result |
| --- | --- | --- |
| Exact correlated family | Axes of sizes 3, 1, 5, and 2, with five supplied tuples | Both backends enumerate exactly the five legal members; their complete domains contain 30 members. |
| Boolean encoding and reordering | Six Boolean variables, explicit reverse reordering, and all 64 Boolean assignments | Only the supplied legal tuples satisfy the relation after reordering; unused encodings remain excluded. |
| Complete profile and replay | A policy with four alias sorts, two state bits, first-match rules, negation, and simultaneous updates; a 135-member family and a deliberately reordered 13-member correlated subfamily | Eight complete profiles, 592 binding results, and 584 replay rows agree with independent equations and product search. |
| Admission before universal exclusion | Four hidden target states and two requests; the first cell excludes all four supplied bindings | Both backends admit all eight target cells before constructing the one mismatch predicate needed to classify the family. |
| Exact resource bounds | Use the measured work and conditional-operation counts as caps, then lower each cap by one | Exact caps succeed; insufficient caps return `inconclusive` without a partial profile. |
| Missing-edge priority | Retain first-cell universal exclusion but remove a later reachable edge | Both backends reject before classification and report the missing-edge word `[1, 1, 1, 0]`. |

The 592 binding results have the denominator
`2 backends × 2 caller settings × (135 + 13 family members)`. They are not
592 independent policies or application samples. Each 135-member family has
one matching binding and 134 exclusions; each 13-member family has one
matching binding and 12 exclusions. The script compares family order,
classification, selected shortest words, lengths, requests, reference and
target outputs, and equality flags. Caller-bearing traces also compare
reference, target, and caller state fields.

The policy oracle interprets the rules directly and searches reference state,
target state, and caller state with its own BFS. It does not call the
implementation's reference evaluator, compiler, grouping algorithm, or profile
traversal. The target table is also built from those independent equations.
Representation and budget checks intentionally inspect internal diagram
interfaces to verify exact sets and ordering of operations.

## Scope of the result

All 584 exclusions in the mixed-sort fixture have one-request witnesses. The
partial caller and its disabled requests participate in admission, but these
results alone do not establish correctness of multi-request caller replays.
They are bounded independent checks, not an exhaustive proof of every policy
or implementation path.

The budget fixture measured 41 work operations in each backend. Its finite-domain
backend counted 15 recursive finite-domain ITE invocations; CUDD counted 35
Boolean ITE interface calls. Those are different units and do not measure
interchangeable primitive operations.

CUDD's node cap is checked after each Boolean ITE returns, and `peak_nodes`
records maxima at those boundaries. Neither quantity bounds transient CUDD
allocations inside an operation or the process's memory use. The script checks
exact work and conditional-operation bounds; it does not claim to have verified
a hard memory ceiling. Dynamic reordering is enabled, and the representation
check additionally forces a reverse ordering.
