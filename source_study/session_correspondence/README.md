# Native session correspondence study

This experiment connects complete-family diagnosis to a larger correlated
family at the same executable source boundary as the session lifecycle study.
It calls the unmodified `SessionsBase.get_user_id` and `remove_session` methods
through their native ORM and SQLite. The separate omitted-delete arm changes
the deletion statement in memory and is an introduced fault control.

Two through six owned, unexpired session rows belong to one user. A candidate
binding is a bijection between presented credential labels and identified
store rows. The supplied families therefore contain 2, 6, 24, 120 and 720
members. These are explicit review hypotheses, not a sample of ambiguous
deployments. The experiment measures scaling within one source interface;
it does not count the five row configurations as five applications.

Every reachable store is reached by native request execution from the complete
initial store. The collector resets the database, replays the stored prefix and
executes each next request, retaining the selected row, return value and full
before/after rows. It then constructs the target table from these records.
Policy evaluators are imported only after acquisition has been written.

The independent oracle uses direct session equations and an explicit
reference–target–caller search. It imports no production evaluator, compiler,
support routine, family traversal or replay. It checks the entire profile,
including each selected shortest word and each replay row. The caller study
compares unrestricted use, lookup-only use and at most one removal. A second
observation retains selected-row identity to show how the observed requirement
changes the first distinguishing request.

Additional families fix the first one through five correspondences, as
applicable to each row count. A separate inconsistent first-row anchor checks
the case where the supplied alternatives exclude the actual correspondence.
The grouped total and one-removal profiles must equal the exact restriction
of the independently checked complete profile.

The native replay phase runs each different shortest physical word once per
case, then compares those source records separately under every excluded fixed
binding selecting that word. This avoids counting repeated hypotheses as
independent source executions.

## Reproduce

Use the environment installed from
`source_study/historical_h19/requirements.lock`. From `artifact/`, run:

```sh
python -B source_study/session_correspondence/run.py --output results/session-correspondence-new
```

The default run covers all five session counts and seven rotated timing
repeats. Each timing repeat uses a fresh process for each of ten methods:
four total-table methods, and scan/grouped caller methods for three caller
languages. Every timed complete profile is compared exactly with the
independently checked retained output after the diagnosis clock stops.

The stages can also be run separately with `--phase acquire`, `analyze`,
`replay`, or `benchmark`, using the same output directory. Acquisition and
native witness replay need the native environment. Analysis and timing require
the artifact's standard-library Python code. Output directories for acquisition
and timing must be fresh; existing native records are never overwritten.

Diagnosis timing includes validation, family normalization, graph admission,
reference evaluation, index maintenance and all witness replay. It excludes
native acquisition, process startup and input parsing. Output serialization
and the complete native acquisition time have their own records. Sample
minima and maxima describe observed variation on the measurement host.

Here, family work inside the clock means validation, normalization and copying
of the supplied list. Permutation enumeration and contract/caller construction
are common input preparation, measured in `analysis-runtime.json`. Worker
modules are loaded before each process begins its per-case clocks. Native
acquisition time includes both arms, source loading, temporary database setup,
prefix replay and finite-table construction; the common dependency gate and
final JSON encoding/write are outside that clock.

## Results

The baseline records 2,808 distinct source cells across 124 reached stores;
the introduced controls add 90 cells across five stores. Reaching the baseline
cells requires 7,536 additional prefix operations. The n = 2 case overlaps
the earlier two-row lifecycle experiment; these counts describe the expanded
cohort and should not be added to the earlier lifecycle count as disjoint data.

All 17,440 per-binding comparisons across ten methods match the independent
product search. Eighty anchored-family profiles add 1,408 exact restriction
checks. The source replays comprise 20 distinct request words and 35 actual
operations, checked separately under 1,739 excluded bindings.

For six sessions, lookup-only use retains all 720 supplied bijections. With
at most one removal, one correspondence remains and the other 719 have
two-request witnesses. Five different words cover these exclusions, with
multiplicities 600, 96, 18, 4 and 1. Adding selected-row identity to the
observation distinguishes the excluded correspondences in one request.
Correctly fixing the first successive rows reduces the family from 720 to
120, 24, 6, 2 and 1; an incorrect first-row anchor leaves no matching member.

The physical test count has a matching lower bound. Under these lifecycle
equations, `n - 1` independently reset words are necessary and sufficient
to exclude every nonidentity bijection when each word has at most two
requests. The ordered diagonal words first exclude
`(n - i + 1)! - (n - i)!` bindings. With selected-row identity, the same
minimum number of one-request lookups suffices. The proof is in
`proofs/session-distinguishability.md`; its independent, standard-library
audit exhaustively checks all declared short words and every smaller test
subset for `n = 2..6`. These are equation-based checks, separate from the
native acquisition and replay counts above.

### Acquisition-associated timing records

The timing below belongs to this study's original ten-method campaign.
The manuscript's current cost comparison uses the separate six-algorithm,
158-task campaign in `results/symbolic-comparison/`, including these same
session inputs. The two campaigns have separate process records and must not
be combined or selected between when reporting a performance result.

The acquisition-associated seven-repeat campaign contains 70 fresh processes and 700 case
records. At six sessions, total-table support grouping reduces reference calls
from 25,221 to 13,802, while retaining 1,438 replay steps. Product and grouped
median diagnosis times are 352.706 and 275.883 milliseconds; their observed
ranges overlap. Under the unrestricted caller, scan/grouped medians are
378.626/242.476 milliseconds and observed ranges are 314.892–438.529 and
207.305–312.531 milliseconds. Lookup-only use makes all aliases relevant at
the live initial store, so both caller methods make 9,360 reference calls and
grouping increases the median from 137.217 to 185.131 milliseconds. The
two-session total-table case also retains its negative result: 0.595
milliseconds for product search and 0.888 for grouping.

## Files

- `fixtures.json`: owned input rows, requests, families and callers.
- `native-observations.json.gz`: complete native graph records and prefixes.
- `acquisition.json`: acquisition runtime and native source/dependency route.
- `inputs.json.gz`: acquired finite tables, supplied contracts and complete
  independently checked expected profiles.
- `profiles.json.gz` and `diagnosis.json`: every binding result and its summary.
- `native-witness-replay.json.gz` and `native-replay-summary.json`: actual
  shortest-word execution and per-binding comparison counts.
- `timing-trials/`, `timing-processes.json` and `timing.json`: every raw process
  result and the derived diagnosis, CPU and serialization summaries.
- `analysis-runtime.json`: common input preparation and validation-campaign
  runtime, kept separate from per-case diagnosis.
- `case-summary.csv` and `timing-summary.csv`: reproducible tables with ten
  case rows and 100 case/method rows; time columns explicitly use milliseconds.

Recompute the tables after checking the raw records:

```sh
python -B source_study/session_correspondence/summarize.py --write-tables
```

Omitting `--write-tables` verifies the existing tables without writing files.
The verifier rechecks native rich observations and all independent binding
answers, then recomputes timing summaries from the retained process outputs.

Focused tests are in `tests/test_session_correspondence.py`. Their direct-equation
tables are unit-test inputs; the scientific experiment's targets come from
native source execution.
