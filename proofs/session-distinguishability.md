# Session correspondence profiles and minimum covers by short tests

The native session study admits all bijections between independently identified
rows and credential labels. This note derives its profile and the cost of
covering every excluded member with shortest physical tests. The accompanying
audit evaluates direct observation equations and imports no production
evaluator, compiler, diagnostic search, fixture, or native adapter.

## Observation equations

There are n rows and n credentials. Initially every row is present, the tokens
are distinct, and successful lookups return the same user. The fixed clock and
nonrenewing requests keep the rows unexpired. Rename rows and credentials so
that the physical correspondence is identity.

A candidate permutation beta maps **row to credential**: beta(i) is the
credential assigned to row i. Equivalently, lookup(j) selects beta inverse(j)
when that row is present. The existing contract names this coordinate
credential-for-row-i. A binding does not change during a word.

Let H be the set of present rows. Removal R_i allows and sets H to H minus {i},
independently of the binding. Lookup L_j preserves H and allows if and only if
beta inverse(j) belongs to H. The physical equations substitute identity for
beta. The decision/presence observation records the decision and the entire
resulting set H. The richer observation additionally records the selected row,
or no row when selection fails. Removal selects no row.

The full declared alphabet crosses lookup/remove with credential-1 through
credential-n, missing, and row-1 through row-n. A lookup of missing or a row
label denies and selects no row. A removal of missing or a credential label
allows and leaves the store unchanged. These requests are included in the
enumeration rather than silently discarded.

The lookup-only caller admits every word containing only lookup requests. The
one-removal caller admits every word with at most one remove request; a removal
with no effect still consumes the allowance. The unrestricted caller admits
every word over the declared alphabet.

Each test word begins with a **fresh complete initial store**. Tests do not
inherit deletions from previously executed tests. The cover cost is the number
of such words with a stated length bound, each holding one candidate binding
fixed. It is not the cost of an arbitrary-length combined execution or a
general test-suite optimization problem.

## Complete profiles

Lookup-only words keep H complete. Every credential therefore allows under
every bijection, and all n! candidates match on every lookup-only word. This
argument is an invariant, not an inference from the absence of a short failure.

Initial observations and all one-request words agree under every candidate.
Removals have binding-independent post-states, while the first lookup sees
every row. After R_i only row i is absent. The reference L_j denies exactly
when beta(i)=j; the physical L_j denies exactly when i=j. Hence R_i L_j agrees
exactly when these two equality propositions have the same truth value.

In particular, R_i L_i excludes exactly the candidates with beta(i) different
from i. Every nonidentity moves some row, so the one-removal caller
leaves only identity. All excluded candidates have shortest length two.
Identity satisfies the equations at every store and request and therefore
matches under the one-removal and unrestricted callers.

Apply the diagonal tests R_1 L_1, ..., R_(n-1) L_(n-1) in order. After i-1
tests, the remaining permutations fix i-1 coordinates and number
(n-i+1)!. Test i retains (n-i)! of them. Its disjoint first-exclusion class
therefore contains

    (n-i+1)! - (n-i)!

members. Fixing n-1 coordinates fixes the last, so these tests cover every
nonidentity. For n=6 the classes have sizes 600, 96, 18, 4 and 1.

## Minimum number of shortest tests

All words of length at most two outside the form R_i L_j are uninformative
under decision/presence observation. Empty and one-request words agree. Two
lookups leave the initial state unchanged; two removals have effects independent
of beta; a lookup before removal sees all rows; and a no-op removal cannot make
the following lookup distinguish a correspondence. The other lookup resources
select no row under every binding. The n squared words R_i L_j are precisely
the informative short tests.

Consider a set of informative tests covering every nonidentity. Suppose it
contains d different diagonal tests and let m=n-d. Each transposition of two
of the m other coordinates passes all diagonal tests in the set. A nondiagonal
test R_i L_j can exclude at most one of these transpositions: the one swapping
i and j. Therefore the set must contain at least binomial(m,2) nondiagonal
tests, for a total of at least

    d + binomial(m,2)
      = n - 1 + (m-1)(m-2)/2
      >= n - 1.

The inequality holds for every nonnegative integer m, including zero, one and
two. The diagonal construction attains n-1. This proves minimum cover size
among words of length at most two. It does not assert uniqueness of an optimal
cover; for example, suitable mixtures of diagonal and nondiagonal tests can
also attain the bound.

## Selected-row observation

In the complete initial store, lookup(j) selects beta inverse(j) in the
reference and j physically. It agrees on selected identity exactly when
beta(j)=j. Its exclusion set is consequently identical to the projected test
R_j L_j. Every nonidentity now has shortest length one, even under lookup-only
calling, and the first n-1 credential lookups give the same factorial strata.

These n-1 lookups are also a minimum cover among words of length at most one.
Only the n credential lookups are informative single requests. Fewer than n-1
distinct ones leave two coordinates unqueried; swapping those coordinates
passes every selected test. The upper bound follows from fixing n-1
coordinates. The same conclusions apply to the unfixed coordinates after k
correct correspondences have been established; zero or one remaining coordinate
needs no additional test.

## Independent exhaustive checks

To recompute and verify the retained evidence without writing, run from the
artifact directory:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --verify-retained results/session-distinguishability

This checks the scientific summary fields, both CSV files and every retained
matrix, profile and cover. Only the recorded start and elapsed time are excluded
from equality comparison. The script requires only the Python standard library
and uses no temporary files. To save another run, provide a new output path:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --output results/session-distinguishability-reproduction

An existing output path is rejected before enumeration. One of --output and
--verify-retained is required; the driver has no default write destination.
The complete audit has the following denominators:

| Sessions | Permutations | Alphabet | Words of length 0–2 | Binding/word pairs | Smaller projected cover subsets | Smaller selected-row cover subsets |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 2 | 10 | 111 | 222 | 1 | 1 |
| 3 | 6 | 14 | 211 | 1,266 | 10 | 4 |
| 4 | 24 | 18 | 343 | 8,232 | 137 | 11 |
| 5 | 120 | 22 | 507 | 60,840 | 2,626 | 26 |
| 6 | 720 | 26 | 703 | 506,160 | 66,712 | 57 |

The 1,875 size-tagged words include the empty word, every one-request word,
and every ordered pair from the complete alphabet. All 576,720 binding/word
pairs are compared under both observations, giving 1,153,440 comparisons.
One-removal and lookup-only profiles filter these same complete word records
according to their caller languages; they do not change the binding.

For the positive all-words results, the audit also checks 10,948 lookup-only
closure cells at the complete initial store and 2,808 identity cells across
every store and request. These are direct-equation checks. They add no native
source executions, even though the latter count equals the number of native
baseline cells acquired by the existing study.

The complete short-word matrix first establishes that the projected exclusion
set is empty for every word outside the n squared informative pairs. It then
enumerates every subset of those pairs with cardinality from zero through n-2,
not just subsets of the diagonal construction. The exact number is

    sum(k=0..n-2) binomial(n*n,k).

Across the five sizes this is 69,486 subsets, with no cover. The corresponding
selected-row enumeration examines all subsets of the n informative single
lookups with cardinality zero through n-2, totaling 99 subsets, again with no
cover. Both constructive covers are checked against every permutation, including
their disjoint first-exclusion memberships and factorial counts.

The retained files in results/session-distinguishability are:

- summary.json: parameters, per-size and total counts, closure checks and run time.
- case-counts.csv: one complete count row per session size.
- minimum-cover-counts.csv: every enumerated subset cardinality and its count.
- complete-enumeration.json.gz: all permutations, requests and words; both
  observations' exact exclusion sets; all caller-specific profiles; and the
  constructive covers with each newly excluded member.
- README.md: reproduction command, count table and indexing conventions.

Request and permutation references are zero based. Row and credential numbers
are one based. A null shortest_word in a profile denotes equivalence, supported
by the separately checked positive-case obligations. No native performance
claim or general test-suite optimum is derived from the enumeration. The
parameterized proofs above establish the result for arbitrary n; the finite
audit checks its implementation-independent instances for n=2 through n=6.
