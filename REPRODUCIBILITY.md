# Reproducing AuthRefine

Run commands from the repository root (`artifact/`) unless stated otherwise. Use fresh output paths;
scientific commands preserve existing datasets. Set
`PYTHONDONTWRITEBYTECODE=1` and use `python -B` so child processes leave the
source tree unchanged.

## Review-facing profiles

Run the self-contained scientific core in a fresh output directory:

```bash
python3 -B evaluate.py --profile core --output /path/to/fresh-output
```

The core evaluator isolates every selected unittest module and runs it in ordinary, `-O`, and `-OO -W error` modes.  Each mode executes 183 checks: 169 pass and 14 explicitly named optional-native or CUDD checks skip.  The portable profile expands the same isolated gate to all 72 self-contained top-level modules, executing 824 tests per mode (800 pass, 24 explicit skips).  The core also verifies the motivating example, selected independent evidence, source-observer scientific files and byte-identical regeneration of all 16 vector figures.  `run_campaign.py` freshly recomputes the 10,000-case finite campaign.

The strict integration superset is:

```bash
python3 -B evaluate.py --profile full --output /path/to/fresh-output
```

This profile first checks the exact package versions and native tools.  If that environment is unavailable, the receipt stops at preflight with status `UNAVAILABLE`; later tests are recorded as not run rather than failed or skipped.  The detailed scope and current status are in `ARTIFACT_EVALUATION.md` and `status.json`.

## Environment

Use Linux CPython and install `requirements-test.txt` into an isolated
environment for the complete test suite. The finite checker and independent
table audits use the standard library. Native source execution needs the
separate locked environment described in [DEPENDENCIES.md](DEPENDENCIES.md).

```sh
python3 -m venv /tmp/authrefine-checks
/tmp/authrefine-checks/bin/python -m pip install -r requirements-test.txt
export PYTHONDONTWRITEBYTECODE=1
/tmp/authrefine-checks/bin/python -B verify_release.py --output /tmp/authrefine-check
```

The verifier checks the supported runtime, scientific inputs, JSON readability,
the ordered 10,000-record campaign, executable example evidence and the
discovered test suite in ordinary and optimized modes. It also runs the
complete credential, source-body, six-method evidence and initial-store
verification commands. Native-dependent tests
report explicit skips in the core environment. Run those subsets again under
their required native environment; a skipped test is not an executed check.

## Core campaign

A single fresh reconstruction is:

```sh
python3 -B reproduce.py --output /tmp/authrefine-campaign --compare results
```

It must produce forty chunks and 10,000 ordered primary records, reconstruct
the documented auxiliary campaigns and report scientific-field agreement.
Only the declared environmental timing and resource fields are excluded from
that semantic comparison. Wall time and CPU time use seconds; Linux peak RSS
uses KiB. They do not determine semantic acceptance.

For the complete deterministic matrix:

```sh
python3 -B verify_release.py --campaign --output /tmp/authrefine-campaign-matrix
```

This copies the artifact into an isolated temporary directory and reconstructs
the campaign for both declared Python hash seeds and both UTC/Los Angeles
time zones. Complete child outputs and failures are retained under the chosen
output directory. The command verifies actual results, including chunk
membership, case order and comparison fields, rather than accepting a process
exit alone. Existing historical records are never relabeled as a fresh run.

## Independent algorithm checks

```sh
python3 -B proofs/audit_support_indexed.py --output /tmp/authrefine-support
python3 -B proofs/audit_support_overlap.py --output /tmp/authrefine-overlap
python3 -B proofs/protocol_family_audit.py --output /tmp/authrefine-callers
python3 -B proofs/audit_protocol_grouping.py --output /tmp/authrefine-caller-groups
```

The first checks 23,040 policy/target pairs against direct semantics. The
second exercises overlapping alias supports and every nonempty subfamily of
eight bindings. The third checks 18,225 one-request partial-target/caller
families. The fourth checks the grouped caller implementation on that existing
domain and a separate 123,930-case overlapping-support domain. Every complete
profile comparison includes the selected word and all fixed-binding replay
fields. Domain inputs and compressed row-level results accompany their summaries.

The original fixed-binding caller check is separately reproducible:

```sh
python3 -B proofs/protocol_audit.py --output /tmp/authrefine-protocol-audit.json
```

The Lean sources and their statement map are in [proofs/README.md](proofs/README.md).
Use an installed compatible Lean compiler; no proof command downloads one.

The session short-test theorem has a separate direct-equation audit:

```sh
python3 -B proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --verify-retained results/session-distinguishability
```

This read-only command recomputes all retained short-word matrices, complete
profiles and smaller-cover enumeration. It uses no production evaluator or
source adapter. Use `--output /tmp/authrefine-short-tests` in place of
`--verify-retained results/session-distinguishability` to save a new run;
existing destinations are rejected.

The operational session request-cost theorem has its own standard-library
audit:

```sh
python3 -B proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
```

It recomputes all 124 correct anchor contexts for two through six sessions,
2,369 anchored binding cases and 1,290 fixed-transposition certificates over
458,854 closed-domain transitions. A separate BFS checks minimum uninterrupted
word lengths for two, three and four sessions. The general bound for adaptive
choices and resets follows from the invariant proof, rather than an enumeration
of unbounded strategies. The audit also reconciles 30 previously acquired
native graph edges along five constructed words. That read-only composition
adds no native execution or timing benchmark. See
`proofs/session-operation-cost.md` for the contract and cost assumptions.
Use `--output /tmp/authrefine-session-operation-cost` in place of
`--verify-retained results/session-operation-cost` to save a fresh independent
audit; existing destinations are rejected.

The extension to arbitrary initial stores includes an independent equation
audit and a separate native collection:

```sh
python3 -B benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
python3 -B source_study/session_initial_state/run.py verify --input results/session-initial-state
```

The first reruns 180 optimal belief-state searches, all 5,456 initial/anchor
contexts, and complete-language product checks. The second checks every native
history under every supplied fixed binding using independent equations and
the declared observation projection. Full row contents validate source
execution; only the declared fields eliminate candidate correspondences.
Both commands preserve the retained files. To acquire new native histories,
use the Piccolo environment described below:

```sh
python -B source_study/session_initial_state/run.py acquire --output /tmp/authrefine-initial-stores
python -B source_study/session_initial_state/run.py verify --input /tmp/authrefine-initial-stores --report /tmp/authrefine-initial-store-check.json
```

Complete restoration and reset-to-initial rebuild fixtures. Their counts are
separate from production lookup/removal requests, and every comparison keeps
one binding and the entire earlier observation history across those operations.

## Native source and witness execution

Install `source_study/historical_h19/requirements.lock` in a separate
environment. With that environment's Python:

```sh
python -B source_study/stateful_sequence/run.py --output /tmp/authrefine-native-session
python -B source_study/session_correspondence/run.py --output /tmp/authrefine-correspondences
python -B -m unittest discover -s tests -p 'test_stateful_sequence.py' -v
python -B -m unittest discover -s tests -p 'test_session_correspondence.py' -v
```

The correspondence command acquires actual ORM/SQLite observations before
loading policy evaluators, checks the complete families with independent
equations, executes each distinct shortest physical request word and measures
ten diagnosis methods with seven rotated fresh-process repetitions.
It retains raw source records, full profiles, all timing samples and separate
common preparation/acquisition costs. The README in that study gives the
precise overlapping and nonoverlapping denominators.

The published-patch experiment uses two separate ORM environments. Follow
`source_study/historical_h19/README.md` to run both and compare the resulting
metadata, SQL and serialized observations. The independent observer for
Healthchecks, Pretix and Wger is runnable without those ORM environments:

```sh
python3 -B source_study/independent_observer/run.py --output /tmp/authrefine-source-observer
python3 -B -m source_study.verify_source_observer --results /tmp/authrefine-source-observer --output /tmp/authrefine-source-observer-check.json
```

Under the same native Piccolo lock, the selected-row observation study is:

```sh
python -B source_study/session_correspondence/verify_observation.py --acquire --results /tmp/authrefine-observation
python -B -m unittest discover -s tests -p 'test_session_observation.py' -v
```

It records complete richer-observation profiles, native one-request witnesses
and a real duplicate-token control separately from the original timing data.
The verifier checks request indices against the actual replayed operations.

For the complete Conet module, install
`source_study/native_policy_store/requirements.lock` into another isolated
environment, then run:

```sh
python -B source_study/native_policy_store/run.py acquire --output /tmp/authrefine-policy-store
python -B source_study/native_policy_store/run.py analyze --output /tmp/authrefine-policy-store
python -B source_study/native_policy_store/run.py replay --output /tmp/authrefine-policy-store
python -B source_study/native_policy_store/run.py verify --output /tmp/authrefine-policy-store
python -B -m unittest discover -s tests -p 'test_native_policy_store.py' -v
```

Actual reaching prefixes and ordered in-memory/file records precede policy
analysis. The same experiment imports and executes the complete source repair,
checks independent set equations, and replays both full-observation and
Boolean-only shortest failures through real instances.

For native Healthchecks HTTP execution, install
`source_study/native_healthchecks/requirements.lock` into its own environment:

```sh
python -B -m source_study.native_healthchecks.run all --output /tmp/authrefine-healthchecks
python -B -m unittest discover -s tests -p 'test_native_healthchecks.py' -v
```

This acquires the complete 120-case configuration grid through the native
Django client, checks two observation contracts and three prefix callers,
replays all reported negative prefixes from fresh databases, and executes
the 30 unchanged upstream get-check, pause and resume tests. The retained
records include each physical SQLite file, full request/response data,
operation-level SQL, source-control diffs and production codebooks. Set
`TMPDIR` to a writable directory if the environment restricts temporary files.

The complementary complete three-request history study uses the same native
Healthchecks environment and a separate fresh output directory:

```sh
python -B -m source_study.native_healthchecks_tree.run all --output /tmp/authrefine-healthchecks-tree
python -B -W error -m unittest discover -s tests -p 'test_native_healthchecks_tree.py' -v
python -B -W error -OO -m unittest discover -s tests -p 'test_native_healthchecks_tree.py' -v
```

It executes all words of length at most three over read-only GET, write PAUSE
and write RESUME from new and paused initial states. The 60 trees retain 2,400
complete physical checkpoints and 2,340 primary HTTP requests; each child
starts from its actual parent's full SQLite image and cookies. The reference
advances independently along the expected path. All 396 first-conflict results
are reproduced by 312 fresh native words containing 732 HTTP requests.
The 21-test suite includes two additional native tree executions in each
interpreter mode. Full experiment inputs remain in
`results/native-healthchecks-tree/`; independent audit records are in
`results/native-healthchecks-tree-review/`; final test and standard-library
verification receipts are separate in
`results/native-healthchecks-tree-validation/`. See
`source_study/native_healthchecks_tree/README.md` and its `ENCODING.md` for the
declared language, observation projection and production bounds.

## Verify retained evidence without new application or timing campaigns

```sh
python3 -B verify_research_depth.py --output /tmp/authrefine-retained-evidence.json
python3 -B source_study/replay.py check
python3 -B benchmarks/audit_credential_admission.py --mode check
python3 -B -m source_study.verify_source_observer --results results/source-observer
python3 -B source_study/session_correspondence/summarize.py
python3 -B source_study/session_correspondence/verify_observation.py
python3 -B source_study/native_policy_store/run.py verify --output results/native-policy-store
python3 -B -m source_study.native_healthchecks.run verify --output results/native-healthchecks
python3 -B -m source_study.native_healthchecks_tree.run verify --output results/native-healthchecks-tree
python3 -B proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review
python3 -B proofs/audit_native_healthchecks.py --results results/native-healthchecks
python3 -B proofs/audit_session_distinguishability.py --sizes 2 3 4 5 6 --verify-retained results/session-distinguishability
python3 -B proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
python3 -B benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
python3 -B source_study/session_initial_state/run.py verify --input results/session-initial-state
python3 -B benchmarks/symbolic_comparison.py --verify results/symbolic-comparison
python3 -B benchmarks/audit_symbolic_comparison.py --verify-review results/symbolic-comparison-review
python3 -B references/verify.py
```

The first recomputes finite profiles and checks retained session, patch and
cost data. The correspondence summarizer independently recomputes native
record equations, complete profiles, anchored families, physical witness
comparisons and every timing summary. It checks the two CSV tables without
writing them; `--write-tables` regenerates those derived tables. The reference
tool checks bibliography identity, included citations, claim locations and
recorded reading scope.

The source-body verifier reexecutes the selected CPython functions on owned
SQLite records, followed by the production comparison and eight source
controls. It preserves the retained evidence and does not load Django or
complete application modules. These commands do not reacquire native
application or timing campaigns or perform new external literature readings.

The credential admission audit can be acquired again in the native
Healthchecks environment, using Python 3.12+ and
[its dependency lock](source_study/native_healthchecks/requirements.lock),
which pins Django 6.1.2:

```sh
python -B -W error benchmarks/audit_credential_admission.py --mode all --output /tmp/authrefine-credential-admission
python3 -B -W error benchmarks/audit_credential_admission.py --mode check --results /tmp/authrefine-credential-admission
```

The complete run executes all 1,260 original contexts through the selected
IR bodies and actual Django ORM/SQLite primitives, then two private serializer
type controls. The baseline matches the retained observations; the new gate
rejects both controls despite the frozen collector's earlier equality result.
The audit preserves that collector and its original source identity. Its
read-only mode checks all seven files without importing Django. These are
rechecks of the existing experiment and two admission controls, separate from
the full native HTTP study.

## Costs and figures

The manuscript's unified six-method comparison uses the optional compiled
symbolic dependency lock. With that environment's Python:

```sh
python -m pip install --only-binary=dd -r requirements-symbolic.txt
python -B benchmarks/symbolic_comparison.py --output /tmp/authrefine-symbolic-comparison --repeats 7
python -B benchmarks/audit_symbolic_comparison.py --results /tmp/authrefine-symbolic-comparison --controls
python -B -m unittest discover -s tests -p 'test_symbolic_family.py' -v
python -B proofs/audit_symbolic_family.py
```

The input is the frozen union of 38 earlier controlled/source tables,
forty session/caller tasks and eighty policy-file/caller tasks. Six methods
apply to total tables and four to caller tasks, giving 760 method/task pairs
and 5,320 measured records in seven rotated repetitions. All complete outputs
are compared after the diagnosis clock; serialization has its own clock.
Native acquisition and input decoding are outside those clocks. Pause other
study runs during timing, retain every trial, and report observed extrema
without attaching a population confidence level.

The independent evidence auditor reconstructs the complete task set from the
original inputs and checks every retained binding, worker schema, process
receipt and derived statistic. It distinguishes Boolean and integer values
and rejects missing or duplicate task records. The retained review includes
42 malformed-record and three positive admission controls. This read-only
verification adds no timing samples or application executions.

The earlier four-method campaign remains independently reproducible:

```sh
python3 -B benchmarks/stateful_family.py --output /tmp/authrefine-family-cost --repeats 7
python3 -B benchmarks/analyze_trial_variation.py --results results/family-cost --output /tmp/authrefine-trial-variation
```

The controlled family benchmark isolates graph sharing, semantic sharing,
index maintenance and full replay. The native correspondence study connects
those costs to acquired source tables. Permutation enumeration is common
input preparation in the latter; measured diagnosis includes validation and
normalization of the supplied family. Report both beneficial and adverse
workloads. Observed minima and maxima have no attached population confidence
level.

See [figures/README.md](figures/README.md) to regenerate every statistical
figure from retained inputs. With the separately distributed manuscript sources
placed at `../paper/`, build the main paper and the supplement with
`python3 -B build.py` there and review the rendered pages at their actual
figure widths. Scientific agreement, bibliography support and visual
inspection are distinct checks.

## Available source material

The [source-study guide](SOURCE_STUDY_GUIDE.md) maps the current source replay
entries and supplementary coverage figure. It preserves the original
source-study README as a checked study input.

Bundled upstream source retains its notices. Optional enterprise replay needs
the separately licensed source described by its study. Older equality-coded observations retain their original scope; unavailable
observer fixtures are not reconstructed by another experiment. Current studies include explicit source
inputs, observation recipes and independent comparisons wherever their README
states that receiver replay is available.
