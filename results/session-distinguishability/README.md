# Session correspondence distinguishability

The retained run passed all direct-equation, complete short-word, closure and
minimum-cover checks for session counts 2, 3, 4, 5, 6.
The proofs are in ../../proofs/session-distinguishability.md and the paper's
technical/session-distinguishability.tex. These records contain no new native
source executions; the existing native session records instantiate the equations.

## Verify the retained records without writing

From the artifact directory, run:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --verify-retained results/session-distinguishability

This recomputes the scientific summary fields, complete matrices, profiles and
both CSV files. The recorded starting time and elapsed time are not compared.
The script uses only the Python standard library and creates no temporary files.

To retain a separate run, select a fresh output directory:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --output results/session-distinguishability-reproduction

An existing output path is rejected before enumeration. The output destination
is mandatory; rerunning the audit never silently overwrites a recorded campaign.

## Complete enumeration counts

| Sessions | Permutations | Words of length 0–2 | Binding/word comparisons | Smaller projected cover subsets | Smaller identity cover subsets | First-exclusion counts |
| ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 2 | 2 | 111 | 222 | 1 | 1 | [1] |
| 3 | 6 | 211 | 1266 | 10 | 4 | [4, 1] |
| 4 | 24 | 343 | 8232 | 137 | 11 | [18, 4, 1] |
| 5 | 120 | 507 | 60840 | 2626 | 26 | [96, 18, 4, 1] |
| 6 | 720 | 703 | 506160 | 66712 | 57 | [600, 96, 18, 4, 1] |

Every word starts with all rows present. The projected cover allows at most two
requests per word; the selected-row cover allows at most one. The candidate tests
for minimum-cover enumeration are all informative words in those classes, after
the complete enumeration establishes that the other words exclude no binding.

## Retained records

- summary.json records parameters, exact counts, closure obligations and the run.
- case-counts.csv gives one row per session count.
- minimum-cover-counts.csv gives every exhaustively checked subset cardinality.
- complete-enumeration.json.gz retains every permutation, request and short word,
  its excluded members under both observations, all caller-specific profiles and
  the standard covers with their disjoint first-exclusion memberships.

All request and permutation references in the compressed file are zero based;
row and credential numbers are one based. For an excluded member, shortest_word
is a list of request indices. A null shortest_word denotes a matching member.
The corresponding positive cases have separately checked closure obligations.
