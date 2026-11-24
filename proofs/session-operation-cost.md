# Optimal request cost for session correspondence certification

The short-word result explains why each incorrect session correspondence has
a two-request witness. The operational question is different: how many
requests are needed to rule out every incorrect correspondence? The optimum
below allows longer words, store resets and choices based on earlier
observations. It also identifies when one continuous execution replaces a
collection of fresh-store tests.

## Contract and cost model

There are n independently named rows and n credential labels. Tokens are
distinct and unexpired, lookups do not renew them, the clock is fixed, and
successful lookups return the same user. The initial store contains every row.
Write H for the present rows and choose names so that the physical
row-to-credential correspondence is identity. A candidate bijection beta maps
row i to credential beta(i). It is fixed throughout the whole certification
history, including across resets.

Removal R_i allows and replaces H by H minus {i}. Lookup L_j preserves H and
allows exactly when beta inverse(j) is in H. The physical equations use
identity. Decision/presence observation contains the decision and the resulting
H. Selected-row observation additionally contains beta inverse(j) for a
successful lookup, and no selected row otherwise. Initial observation contains
presence, not the token contents of every row. Other declared request/resource
combinations either deny without selecting a row or allow without changing H.
They supply no extra information.

Let A be a set of k correctly established correspondences and let U be the
other m = n-k coordinates. The candidate family is exactly

    F_A = { beta in S_n : beta(i) = i for every i in A }.

Thus the unanchored coordinates admit every permutation. Anchors are supplied
before this experiment, which starts again from the complete store H = [n].
The cost of discovering those anchors is not included.

A certification strategy may choose its next request from the observations
already obtained. It may also reset H to the complete store, retaining the
same binding and all earlier observations. A successful identity branch may
stop only when no other member of F_A produces the same history. This is sound
certification of identity, not identification of an arbitrary unknown
permutation. The strategy is deterministic as a function of its observed
history; fixing any random choices gives the same lower bound on a sound
branch. Each lookup and removal costs one request. Reset and initialization
costs are excluded from this request count and considered separately below.

## Theorem: minimum requests, independent of word length and resets

**Theorem.** For the contract and family above, the minimum number of requests
on a sound identity-certification branch is

    decision/presence: 2 max(m-1, 0),
    selected-row:       max(m-1, 0).

These minima allow arbitrary finite words, adaptive choices and any number of
fresh-store resets. For m at least two, the decision/presence minimum is attained
without a reset by the continuous word

    R_i1 L_i1 R_i2 L_i2 ... R_i(m-1) L_i(m-1),

where i1,...,im is any ordering of U. The selected-row minimum is attained by
L_i1 ... L_i(m-1). No request is required when m is zero or one.

**Proof of the projected lower bound.** Consider the entire terminating
identity branch. Let D be the unanchored row labels removed anywhere on that
branch and Q the unanchored credential labels queried anywhere on it. These
sets accumulate across resets.

If fewer than m-1 different rows occur in D, choose two coordinates a,b in
U outside D and fix beta to their transposition. This beta respects every
anchor. Both rows remain present throughout the branch and after every reset.
Lookups of a and b therefore allow under both interpretations; all other
credential lookups have the same selected row. Removals have identical named-row
effects, and decision/presence observations agree at every step. Induction on
the observation history makes an adaptive strategy choose the same next
operation under identity and beta. Thus beta survives when the strategy stops,
contradicting certification. At least m-1 distinct free rows must be removed.

If fewer than m-1 different credentials occur in Q, instead transpose two
unqueried credentials. Every queried credential has the same selected row
under both interpretations in every store. Named removals and resets also
agree. The same history induction again leaves this fixed nonidentity member
indistinguishable. At least m-1 distinct free credentials must be queried.
Removal and lookup are different requests, so the two requirements add to
2(m-1). No assumption about a maximum word length or the number of resets was
used.

**Proof of attainment.** After the first t-1 pairs of the displayed continuous
word have agreed, the anchors and i1,...,i(t-1) are fixed. Immediately after
R_it, the deleted rows are exactly i1,...,it. The physical L_it denies. An
agreeing candidate must place credential it in one of those deleted rows.
Previously fixed rows already hold their own credentials, so only row it can
hold it. Therefore this pair fixes beta(it)=it. Induction fixes m-1 free
coordinates; bijectivity fixes the last. The word uses exactly 2(m-1) requests.

For selected-row observation, the unqueried-credential argument remains valid
even if arbitrary removals and resets are permitted: every queried credential
still selects its physical row. It gives the lower bound m-1. From the complete
store, observing row it on L_it is exactly the condition beta(it)=it, so the
first m-1 credential lookups attain it. When m is at most one, F_A already
contains identity alone. This proves all cases.

## Caller restriction: arbitrary-length one-removal runs

**Corollary.** Suppose each fresh-store word is admitted by the one-removal
caller: it may contain at most one removal request, including a removal that
has no effect. Even if each word may be arbitrarily long and later words may
depend on earlier observations, the minimum number of nonempty words needed
for decision/presence certification is max(m-1,0).

**Proof.** Every successful identity branch must remove at least m-1 distinct
free rows by the theorem. Each permitted word can remove at most one. The
fresh-store words R_it L_it attain the bound, each fixing its named free row.

The maximum information available in a single such word can also be stated
exactly. Lookups preceding the removal see the complete store. Following an
effective R_i, querying every credential distinguishes precisely whether
beta(i)=i; every candidate fixing i gives the same full response sequence as
identity. Repetitions or different query orders add nothing. For an unanchored
i, at least (m-1)! candidates therefore survive; removing an anchored row leaves
all m! members. A word with no effective removal is uninformative. For m>2,
no one-removal word can certify identity. The continuous optimal word belongs
to the unrestricted caller and is not a one-removal word in this case.

## First-exclusion strata and individually shortest witnesses

After t-1 agreeing pairs of the continuous construction, (m-t+1)! candidates
remain. Pair t leaves (m-t)!, so its first-exclusion stratum has size

    (m-t+1)! - (m-t)!,  t = 1,...,m-1.

Its first discrepancy occurs at request position 2t. With no anchors and six
sessions, the strata are 600,96,18,4,1 at positions 2,4,6,8,10. These are also
the stratum memberships of the ordered fresh-store pairs, but their positions
in a continuous execution are not the lengths of individually shortest
counterexamples.

For every nonidentity beta, no single projected request distinguishes it
from the complete store, whereas R_i L_i does whenever beta(i) differs from i.
Its globally shortest projected witness consequently remains length two.
Selected-row observation gives length one. A cumulative covering trace trades
multiple initializations for later failure positions of some candidates;
it does not replace the complete profile's individual shortest replays.

The continuous and reset constructions use the same optimal request count.
For m at least two, the former needs one complete-store initialization, whereas
the one-removal construction needs m-1. This is a count of initialization
events, not a measured latency claim.

## Why the hypotheses matter

The complete remaining permutation family is necessary for the transposition
lower bound. With n=4 and family {identity,(2,3,4,1)} in row-to-credential
notation, there is no common fixed coordinate, yet R_1 L_2 excludes the only
incorrect member in two requests. Applying 2(n-1)=6 to that restricted family
would be false.

The fresh complete initial store is also necessary for the stated residual
cost. With two free rows and row 1 already absent, L_1 alone distinguishes
identity from their transposition. That one remaining query does not violate
the theorem: it inherits a deletion performed before the counted experiment.
Correct anchors alone do not specify such a residual store.

## Independent finite audit and retained native-edge reconciliation

`audit_session_operation_cost.py` imports only the Python standard library.
Reference lookup scans the row-to-credential permutation; physical lookup
addresses the named row directly. The audit covers n=2,...,6, all 124 correct
anchor subsets, and 2,369 anchor-context/permutation combinations. For each
case it preserves the reference traces of the continuous projected word,
fresh-store pairs and selected-row word, their first differences, and the
exact survivors after a removal followed by all credential queries. It checks
8,962 reset-pair/binding combinations and 13,690 maximal-one-removal-word/binding
combinations. These are equation comparisons, not new application cases.

The lower-bound certificates instantiate the two induction arguments:

- **Deletion support D.** Choose two free coordinates outside D. Enumerate all
  stores H containing U minus D, permit arbitrary credential queries and
  removals only from A union D, and compare the fixed transposition with
  identity under decision/presence observation. This store domain is closed
  under those requests and contains the complete reset store.
- **Query support Q.** Choose two free coordinates outside Q. Enumerate all
  stores, permit any removal and credential queries only from A union Q, and
  compare the transposition with identity under selected-row observation.
  This equality also implies decision/presence equality. The domain is closed
  and includes resets.

There are 645 certificates of each kind, checked through 458,854 closed-domain
transition comparisons. Each retained certificate includes the fixed
alternative, every admitted store and request, and the comparison count. The
proof chooses D or Q from a complete identity branch and then uses its fixed
transposition throughout; it does not change the candidate between requests.
Finite certificate instances support this proof without claiming an enumeration
of every adaptive strategy or unbounded word.

A separate belief-state BFS checks minimum continuous-word lengths for n=2,3,4.
The state contains the deleted-row set and all surviving fixed permutations;
it exhausts every smaller reachable depth and obtains lengths 2,4,6. It explores
one uninterrupted execution only. The general adaptive/reset bound comes from
the proof and its closed-domain certificates.

The audit also reads the existing baseline session graph. For each n=2,...,6
it follows the unanchored cumulative word through retained edges and compares
the full before/after row records, request arguments, return values, selected
identities and graph observations. Thirty retained edges across five
constructed words compose continuously. Those edges were acquired previously
from their recorded reaching prefixes. Reconciliation is read-only and is
not a new end-to-end native execution of the longer word. Existing acquisition
and benchmark records remain unchanged.

## Reproduction

From `artifact/`, verify the retained evidence without writing:

```sh
PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
```

For a new record, use a fresh destination:

```sh
PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_operation_cost.py --output results/session-operation-cost-reproduction
```

The driver refuses existing output directories before computation and refuses
an output nested inside its retained native-input directory. The read-only
mode recomputes all scientific fields, complete evidence, BFS, native-edge
reconciliation, CSV and README. Only the recorded start and elapsed time are
excluded from comparison. The native input is checked unchanged byte for byte
and by modification time. Neither mode imports or executes native application
code.
