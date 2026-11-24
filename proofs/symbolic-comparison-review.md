# Retained comparison evidence

The independent reader in `benchmarks/audit_symbolic_comparison.py` admits all
retained measurements in `results/symbolic-comparison`: 158 tasks, 760 applicable
task/method pairs, seven repetitions, 42 process records, and 5,320 timed task
records. It also checks all 10,529 retained binding profiles against the four
original scientific input files. The acquisition program and its 89 measurement
files remain unchanged.

## What the reader establishes

The task denominator follows the acquisition contract:

| Cohort | Total-table tasks | Caller tasks | Applicable task/method pairs |
| --- | ---: | ---: | ---: |
| Family cost | 38 | 0 | 228 |
| Session correspondence | 10 | 30 | 180 |
| Native policy store | 16 | 64 | 352 |
| Total | 64 | 94 | 760 |

The two per-binding methods receive the 64 total-table tasks. Scan,
support-indexed, finite-domain, and CUDD each receive all 158 tasks. Every method
has seven separate process receipts. The reader checks the declared rotation of
method order, the complete applicable task order within each process, and the
one-to-one mapping from each receipt to its retained stdout and stderr files.
Missing tasks or processes cannot reduce the admitted denominator.

Every raw worker must contain exactly the seven fields emitted by the historical
worker. Its receipt must contain those same fields and the five parent-recorded
fields. All corresponding values must agree, including scalar types. An integer
return code of zero is required; Boolean `False` and floating-point `0.0` do not
qualify. Timings, process memory, repetition numbers, and work counters also have
explicit integer requirements. Duplicate JSON keys, nonfinite numbers, missing
fields, extra fields, undeclared log paths, symlinked logs, and nonempty stderr
are rejected.

Complete output identity covers each binding, equivalence result, failure length,
request indices, and every replay field. The reader reconstructs the legal family
and checks its order and cardinality before checking the retained output digest
and byte count. Replay records have typed comparison flags, valid request indices,
and the declared first-failure stopping point. This prevents an unchanged failure
length from hiding a changed request or replay. The expected profiles themselves
must match their original scientific inputs.

The reader recomputes every reported median, minimum, maximum, sample list, and
work counter. The sum of a worker's sequential diagnosis and serialization
intervals must fit within the parent-recorded process duration. CPU time is not
compared with wall time. CUDD manager node counts retain their observed sample
variation; stable scientific counters must agree across repetitions.

Each worker's reported Python and platform metadata must match the retained
environment. CUDD workers must report the pinned `dd` package; other methods must
report no CUDD package. The complete nine-file historical source identity set
must match the preserved acquisition implementation, and the dependency package
set must match `requirements-symbolic.txt`.

## Admission regression and controls

The earlier verification helper compared only fields present in a raw worker
object. An empty object therefore supplied no comparisons. It also admitted a
Boolean process return code through Python's equality between `False` and `0`.
Both cases were reproduced on private copies of the retained evidence. The new
reader checks the complete worker schema and strict return-code type before
admitting a process. Keeping the acquisition program intact preserves the source
identity recorded when the measurements were collected.

`results/symbolic-comparison-review/controls.json` records 42 malformed-copy
controls and three positive controls. They cover raw-record completeness,
numeric types, method and repetition coverage, complete-output identity, runtime
and backend metadata, source-identity completeness, and summary reconstruction.
All malformed copies are rejected. The unchanged complete worker, an equivalent
worker with reordered JSON object keys, and the unchanged full campaign are
accepted. These controls add no scientific measurements.

The 17 tests in `tests/test_symbolic_comparison_evidence.py` also exercise the CLI
on actual copied files. They include missing and symlinked logs, duplicate JSON
fields, the empty-worker regression, and Boolean return codes with Python
optimization enabled. Output protection is checked with an existing directory
and a preserved sentinel file. The read-only path preserves both file contents
and modification times.

## Reproduction

From `artifact/`, the standard Python library is sufficient:

```sh
python -B benchmarks/audit_symbolic_comparison.py
python -OO -B -W error benchmarks/audit_symbolic_comparison.py --verify-review results/symbolic-comparison-review
python -B -W error -m unittest discover -s tests -p test_symbolic_comparison_evidence.py -v
```

The first command performs no writes. The second also reruns the admission
controls and compares the result and file inventory with the retained review.
To save an additional review, supply `--controls --output PATH`, where `PATH`
does not exist and its parent does. The reader rejects existing destinations,
symlink routing, and destinations that overlap scientific inputs.

The review establishes consistency of the retained evidence with its acquisition
contract. Runtime and backend identities are the metadata retained by the
original processes: the records contain neither process identifiers nor
executable binary digests. Complete-output hashes bind the worker reports to
the expected profiles; this reader does not rerun the diagnosis algorithms or
independently establish the expected profiles' semantics. Native execution,
semantic validation, and fresh timing remain separate artifact procedures.
