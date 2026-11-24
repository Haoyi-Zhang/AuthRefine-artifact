# Session diagnosis from a partially populated store

This extends the delivered operation-cost result to an arbitrary initial row
set. It retains the same fixed-clock, distinct-token, initially unexpired,
nonrenewing session equations, fixed candidate correspondence and common
successful user identity. The initial observation exposes row presence, not
the token contents of every row.

## Initial state and the two different reset operations

Let A be the correctly anchored row/credential pairs and U their complement,
with m=|U|. The candidate family contains exactly all permutations fixing A.
The physical correspondence is named as identity. Let H0 be the supplied
initial set of present rows, P=U intersect H0 and D=U minus H0. Write p=|P| and
d=|D|, so p+d=m. The placement of anchored rows inside or outside H0 is
arbitrary and known; their correspondences remain fixed.

Removal R_i deletes the named row if present. Lookup L_j returns allow exactly
when beta inverse(j) is present; the rich observation additionally returns that
row's identity when it exists. As in the delivered model, these operations have
no hidden side effects that reveal absent tokens or recreate rows.

Two reset operations have different diagnostic consequences:

- **Restore-to-complete** sets H to all n rows. It recreates the same declared
  rows and credentials, preserves the fixed beta, and preserves accumulated
  observations. It is an explicit reconstruction action, not an ordinary
  lookup or deletion. Each use has cost rho >= 0.
- **Reset-to-initial** sets H back to H0. It never restores rows absent in H0.
  It is distinguished from restore-to-complete even if both are colloquially
  called reset.

Each lookup/removal has unit cost. H0 and the anchors are supplied before the
counted experiment. Costs of establishing them or initially acquiring H0 are
outside this residual question. Strategies may adapt their next action to the
complete observed history; all stated optima concern sound identity-certifying
branches. Fixing randomness gives the same branchwise lower bounds.

## Exact surviving family without restoration

If every execution starts in H0 and no action creates an initially absent row,
the largest family agreeing with identity on the entire indicated language is:

| Observation / permitted operations | Exact survivors | Cardinality |
|---|---|---:|
| Decision/presence, lookup only | beta fixes A and preserves P and D as sets | p! d! |
| Decision/presence, lookup and removal | beta fixes every row in A union P | d! |
| Selected-row identity, lookup only or lookup and removal | beta fixes every row in A union P | d! |

These statements also hold with arbitrarily many reset-to-initial actions.

**Proof.** A projected lookup from H0 agrees for every credential exactly when
membership in H0 is preserved. Anchors are already fixed, leaving arbitrary
permutations inside P and D. This gives the first row.

For the second row, a surviving candidate must first preserve P and D. For
each i in P, the word R_i L_i denies physically. A candidate that preserves P
but does not fix i places credential i in another row of P, which is still
present, and therefore allows. Thus every i in P is fixed. Conversely, if A
union P is fixed, the only remaining permutations involve initially absent
rows. Every later store is a subset of H0; both interpretations return the
same decision and presence for every request. Reset-to-initial remains in
this closed domain.

For selected-row observations, the successful initial lookup L_i already
fixes each i in P. Initially absent credentials return deny with no selected
row, and their rows never become present, so their internal permutations
remain indistinguishable. The same closed-domain argument establishes the
third row. Factorials include 0!=1.

Consequently, two or more initially absent free rows cannot be distinguished
without an action that makes them present. This is a complete characterization
of the residual ambiguity, not merely one counterexample.

## Optimal cost when restore-to-complete is available

For m <= 1, the candidate family is already a singleton and every optimum is
zero, regardless of the initial store.

For m >= 2, let b be 1 when 0<d<m and 0 otherwise. The exact optimal request
and restoration counts are attained simultaneously:

| Observation | Lookup/removal requests | Restorations |
|---|---:|---:|
| Decision/presence | 2(m-1)-b | 1 if d>=2, otherwise 0 |
| Selected-row identity | m-1 | 1 if d>=2, otherwise 0 |

Thus, for any finite rho>=0, the exact weighted costs are

    decision/presence: 2(m-1) - b + rho * 1[d>=2],
    selected-row:     (m-1)     + rho * 1[d>=2].

### Request lower bounds

At least m-1 distinct free credentials must be queried. Otherwise transpose
two never-queried free credentials and fix this alternative for the entire
history. Every queried credential has exactly the same selected row, including
after restorations, and removals/restorations have identical named effects.
The same observed history induces the same choices by an adaptive strategy,
so that nonidentity candidate remains when the branch stops. This argument
applies to both observation modes.

For projected observations, consider two free rows in the same initial
presence class that are never named by a removal request. Their fixed
transposition remains indistinguishable: initially both have equal presence;
each complete restoration makes both present. Resets-to-initial restore their
shared initial presence. Lookups of their two credentials therefore have the
same decision, while all other lookups select the same rows. Adaptivity does not separate equal
histories.

At most one row in each nonempty initial class can therefore be left without
a removal request. If both classes are nonempty, at least (p-1)+(d-1)=m-2
different rows must be named. If there is just one class, at least m-1 must be
named. Lookup and removal are separate requests, giving 2(m-1)-b.

### Restoration lower bound

When d>=2, transpose two initially absent free rows. Until a restoration,
both remain absent; all lookup, removal and reset-to-initial observations
agree, even with selected-row identity. Sound certification therefore requires
at least one restore-to-complete. No restoration lower bound is needed when
d<=1.

### Simultaneous attainment for decision/presence

If d=0, use the original continuous pairs R_i L_i for m-1 free rows. This uses
2(m-1) requests and no restoration.

If p=0, first restore the complete store, then use those same pairs. This uses
2(m-1) requests and one restoration.

Otherwise choose a distinguished absent row a_star in D. First execute
L_a_star from H0; its denial confines that credential to D. Next choose any
ordering b1,...,b_p of P and execute R_bi L_bi for i=1,...,p-1. Each denial
confines credential b_i to D union {b1,...,b_i}.

If d>=2, restore to the complete store and choose an ordering a1,...,a_(d-1)
of D minus {a_star}. Execute R_ai L_ai for each. These post-restoration pairs
fix a1,...,a_(d-1) in order: each later denial can name no earlier fixed row,
because that row already holds its own credential. The initial constraint
then fixes a_star. With D fixed, the earlier b_i constraints fix b1,...,b_(p-1)
in order, and bijectivity fixes b_p. When d=1, the first lookup fixes a_star
immediately and the restoration phase is empty.

The construction uses 1+(p-1)+(d-1)=m-1 lookups and
(p-1)+(d-1)=m-2 removals. It uses exactly one restoration when d>=2 and none
otherwise. The retained observations constrain the same fixed candidate
across both phases, so post-restoration evidence can resolve the earlier
constraints.

### Simultaneous attainment with selected-row identity

If d<=1, query m-1 present free credentials. When d=0, omit any one free row;
when d=1, query all p=m-1 present free rows. Their returned identities fix those
rows and bijectivity fixes the last. If d>=2, restore the complete store and
query any m-1 free credentials. All selected rows are then observable. These
constructions attain both independent lower bounds simultaneously, which
proves the weighted formula for every rho>=0, not just the lexicographic
objective used by the finite search.

## No restoration, or only reset-to-initial

For m>=2, the exact projected optimum is 2(m-1) when d=0 and 2m-3 when d=1.
The exact selected-row optimum is m-1 in both cases. For d>=2 no finite
strategy certifies identity. The constructions above for d<=1 already use no
reset, and the two-absent-row invariant proves the remaining cases. For m<=1
the optimum remains zero.

For example, with two unanchored rows both initially absent, all lookups deny
and all removals preserve the empty store. Repeating reset-to-initial adds no
information. A restore-to-complete changes this: one lookup under selected-row
observation or a removal/lookup pair under projected observation certifies
identity. Thus restoration semantics cannot be omitted from the theorem.

## Independent finite verification

`benchmarks/audit_session_initial_state.py` is a separate standard-library
implementation with no imports from AuthRefine semantics, the native collector,
or the native-study oracle. Its search states are `(physical store, surviving
fixed permutations)`. Search enumerates informative lookups, effective removals
and the declared reconstruction operation; it omits only self-loops that add
no information. It does not consult the formula or the upper-bound word.
The lexicographic objective minimizes requests and then reconstruction count.
The proof above separately establishes both lower bounds, so the weighted
result is stronger than a lexicographic search observation.

The retained finite audit checks:

- Every initial subset at n=1..4, both observations, and no reconstruction,
  reset-to-initial, or restore-to-complete: 180 independent searches,
  57,609 expanded states and 290,536 inspected transitions.
- Every anchor subset and initial store at n=2..6: 5,456 contexts,
  23,284 attainable constructions, 396,960 full fixed-binding histories,
  and 2,033,832 request comparisons. It separately checks 9,452 impossible
  contexts by a fixed absent-row transposition over their closed store domain.
- Every exact surviving family in four observation/operation profiles over
  the same 5,456 contexts: 21,824 profiles, 547,472 independent fixed-binding
  product traversals, 864,098 visited product states and 3,796,745 transition
  comparisons. The audit checks the identities of all surviving permutations,
  not only their cardinalities. Products exhaust the reachable language;
  they do not use a word-length cutoff.

The no-reconstruction and reset-to-initial languages have the same surviving
families because the latter adds only a return to the product's initial state.
All stated finite checks are standard-library executable audits. The
arbitrary-cardinality statements are established by the mathematical proofs
above; no theorem-prover certification is claimed.

## Complete native strategy execution

`source_study/session_initial_state/` executes the unchanged selected session
methods through the existing native Sessions adapter, Piccolo and SQLite.
The scientific cohort contains all 124 initial subsets at n=2..6 under both
observations, with no supplied anchors: 248 complete optimal words,
1,434 production requests and 198 restore-to-complete fixture operations.
The projected words use 918 requests and 99 restorations; selected-row words
use 516 requests and 99 restorations.

Ten further complete words begin with the final two rows absent and include
two actual resets to that same initial subset. They execute 160 production
requests and 20 reset-to-initial fixture operations. Each retains precisely
identity and the transposition of its two absent rows. All reconstructions
are explicit harness operations, not production Session API calls.

The collector prepares each initial store afresh, then records its complete
physical rows, every source request, the before/after rows of each
reconstruction, and the final physical rows. The independent oracle uses a
single fixed row-to-credential bijection for each entire recorded word. A
reconstruction changes the store, never the binding or previously accumulated
comparisons. It evaluates every request even after that binding's first
mismatch. This checks 100,720 fixed-binding histories and 692,432 request
comparisons for the optimal cohort, and 1,744 histories and 40,304 comparisons
for the reset controls.

Raw token contents and other instrumented fields establish that the selected
source and physical records satisfy the declared lifecycle; candidate
elimination uses only decision/presence, or those fields plus selected row
identity in the richer observation. Every optimal word uniquely certifies
identity and attains both theorem counts. The source executions and the
independent finite audit are separate evidence classes. All 258 native words
were executed end to end; no concatenation of previously acquired graph edges
is counted as a new execution.

Acquisition records bind the scientific inputs, raw traces, actual source
manifests, dependency records and the execution/verification code to content
identities captured around execution. They retain UTC start and finish
instants and actual installed dependency metadata. Read-only verification
checks these identities, physical continuity, all observation fields, exact
candidate survivors and exact operation counts. Source admission retains the
unchanged production method bodies; fixing the experiment clock and
reconstructing fixtures remain explicit harness operations.

## Reproduction

From the `artifact` directory, the following commands use only the standard
library and do not change the retained results:

```sh
python -B -W error benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
python -B -W error source_study/session_initial_state/run.py verify --input results/session-initial-state
python -B -W error -m unittest discover -s tests -p test_session_initial_state.py -v
```

A fresh native acquisition requires the existing pinned native dependency
environment and a destination directory that does not exist. See
`source_study/session_initial_state/README.md` for the complete acquisition and
verification commands. Request counts are algebraic operation counts; the
local acquisition duration is not a performance comparison.
