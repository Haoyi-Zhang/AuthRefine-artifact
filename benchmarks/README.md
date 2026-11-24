# Equal-output complete-family comparisons

The manuscript compares six implementations on the same complete diagnostic
output: every legal binding, the canonical first shortest word for every
excluded binding, and all rows of its fixed-binding replay. The current matched
campaign is `results/symbolic-comparison/`.

## Run or verify

Run these commands from `artifact/`. Use an isolated CPython environment with
the optional compiled symbolic lock:

```sh
python -m pip install --only-binary=dd -r requirements-symbolic.txt
python -B benchmarks/symbolic_comparison.py --output /fresh/complete-comparison --repeats 7
python -B benchmarks/audit_symbolic_comparison.py --results /fresh/complete-comparison --controls
```

The independent evidence auditor needs only the standard library. It reconstructs
the declared tasks from four original scientific inputs, checks every complete
binding profile, requires exact worker and process-receipt schemas, and
recomputes all timing summaries. Boolean flags, integer counts and floating
values remain distinct. The runner requires a fresh destination and the actual
compiled `dd.cudd` backend.

To reconcile the included campaign with its retained audit and repeat the
malformed-record controls without writing files:

```sh
python -B benchmarks/audit_symbolic_comparison.py --verify-review results/symbolic-comparison-review
```

This checks 42 worker processes, 5,320 timed records and 10,529 complete binding
profiles; 42 rejection controls and three positive controls accompany the
audit. It checks consistency of recorded runtime and backend metadata, without
rerunning the historical processes. The original acquisition program and its
89 result files retain their recorded identities. See
`proofs/symbolic-comparison-review.md` for the evidence contract.

## Compared implementations

| Method | Shared work | Applicable inputs |
| --- | --- | --- |
| Per-binding product | Independent reference/target BFS per binding | Total tables |
| Per-binding target | Independent target BFS with the same complete state observation | Total tables |
| Scan | One admitted target or target/caller graph | Total and caller tables |
| Support indexed | Graph plus active groups over each cell's local alias support | Total and caller tables |
| Finite-domain | Graph plus exact legal-family and Boolean mismatch diagrams | Total and caller tables |
| CUDD | The same Boolean construction through compiled binary decision diagrams | Total and caller tables |

The first four methods use the same concrete reference evaluator. Both diagram
implementations compile guards and simultaneous effects directly to a Boolean
mismatch predicate. Independent semantic audits are separate from this timing
comparison. CUDD is provided by `dd` 0.6.0 with dynamic reordering enabled; each
diagnosis creates its own manager. Alias order is canonical name order, binary
codes outside an alias domain are excluded, and supplied correlated families
are encoded as exact relations without Cartesian completion.

The diagram comparison implements this particular complete-family algorithm
with two representation backends. It is not a port of a different policy or
product-line tool to an incompatible output contract. Default library setup,
family encoding and Python-to-CUDD operation calls are part of its measured
per-task cost.

## Fixed tasks and denominators

The campaign has 158 tasks from three retained sources:

| Cohort | Construction | Tasks |
| --- | --- | ---: |
| State/support and earlier source tables | 27 sparse controls, 6 dense controls, 1 singleton and 4 source/control tables | 38 |
| Native session correspondences | 10 source/control tables, each total and under 3 callers | 40 |
| Native policy store | 16 initial-file/source-arm tables, each total and under 4 callers | 80 |

The sparse controls cross 2, 8 and 32 reachable states with 2, 16 and 256
bindings and all-matching, late-failure or early-failure regimes. The four
source/control tables contain two Healthchecks resume forms and the earlier
two-session baseline/omitted-delete pair. That pair also occurs in the expanded
session cohort. Additional callers and initial files are tasks on the same
source interface, not additional applications or independent field samples.

Six methods apply to each of 64 total-table tasks; four apply to each of 94
caller tasks. Seven complete rotated repetitions therefore produce 42 worker
processes, 760 method/task pairs and 5,320 timed task records. Each worker runs
all tasks to which its method applies, in fixed input order. Input permutation
lists and native tables are retained exactly as supplied to every method.

## Clocks and correctness checks

Each diagnosis clock includes schema and family validation/normalization,
legal-relation or support-index construction, complete graph admission,
diagnostic evaluation and all individual fixed-binding replays. Module imports,
process startup, JSON input decoding and the comparison with independently
retained expected output are outside that clock. Canonical JSON serialization
has a separate clock. Native source acquisition and dependency installation
are not algorithm diagnosis time.

Every timed output is compared with the complete canonical expected output
before the record is accepted. This checks every binding, selected request
sequence and replay field. A matching classification or shortest-length count
alone is insufficient. The runner freezes relevant implementation identities
across the campaign, and the verifier rejects changed sources or incomplete
method/repeat matrices.

Concrete reference calls, recursive finite-domain ITE invocations and CUDD ITE
API calls have different units. They explain work within an implementation;
they are not interchangeable operations. Recorded CUDD node peaks are checked
manager sizes after ITE calls, rather than transient native allocations or
per-case process memory. Process peak RSS is recorded only for the complete
worker and is not reported as per-task memory.

## Raw evidence and figures

`inputs.json.gz` retains all tasks and `profiles.json.gz` their complete
expected outputs. `trials/` contains every raw worker stdout and stderr;
`trials.json` is their ordered aggregate. `summary.json` contains the medians,
observed minima/maxima and work counters. `environment.json` records the actual
Python, dependencies and implementation identities.

The paper uses these same data for all current complete-profile cost figures:

```sh
python -B figures/family_cost.py --results results/symbolic-comparison --output /fresh/figures
python -B figures/session_correspondence.py --results results/session-correspondence --comparison-results results/symbolic-comparison --output /fresh/figures
python -B figures/symbolic_comparison.py --results results/symbolic-comparison --output /fresh/figures
```

The first figure relates reference-call reductions to time on the 38-table
cohort. The second connects session-family outcomes to caller costs. The third
retains every task in three cumulative cost distributions, comparing scan,
finite-domain and CUDD time with support indexing. Each ratio divides the
methods' seven-run medians on the same task. A task fraction describes that
fixed cohort; observed timing ranges are not confidence intervals.

## Earlier independently retained comparisons

`results/family-cost/` retains the earlier four-method, 38-table measurement,
and `results/session-correspondence/` retains the earlier ten-method/caller
session measurement. Those original records remain unchanged. They are not
pooled with the current complete six-method campaign or used to fill missing
current timings.

```sh
python -B benchmarks/stateful_family.py --output /fresh/family-cost --repeats 7
python -B benchmarks/analyze_trial_variation.py --results results/family-cost --output /fresh/trial-variation
```

The latter checks the earlier 1,064 records and 456 metric summaries. For a
product/indexed point, the displayed observed envelope is
`[min(product)/max(indexed), max(product)/min(indexed)]`. Pause other study
experiments during fresh timing and retain all repetitions, including adverse
cases and failed runs, with their actual status.

## Other evidence audits

Two additional drivers in this directory check observation admission and
initial-store request costs. Their retained checks use the standard library
and do not repeat timing or native application campaigns:

```sh
python -B -W error benchmarks/audit_credential_admission.py --mode check
python -B -W error benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
```

The credential audit checks the complete native baseline and both serializer
type controls in `results/credential-admission-review/`; its fresh acquisition
uses the native Healthchecks environment described in
[REPRODUCIBILITY.md](../REPRODUCIBILITY.md). The initial-state audit performs
independent belief-state searches and complete-language checks. Its proof,
native companion and observation contracts are linked from the
[initial-state study guide](../source_study/session_initial_state/README.md).
