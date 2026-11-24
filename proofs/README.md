# Mathematical arguments and executable checks

`semantics.md` gives the finite-model arguments corresponding to the manuscript.
The total-table active-group invariant is in `SUPPORT_INDEXED_FAMILY.md`;
`PROTOCOL_GROUPING.md` extends it to admitted caller histories. Source
observations and the supplied contract family connect those algorithms to an
application boundary.

## Lean statements

The thirteen included Lean files check selected conditional laws and finite
component obligations. They are not extraction of the Python implementation.
Run them with an installed Lean 4.8.0 compiler into a fresh directory:

```sh
python3 -B proofs/check_lean.py --compiler /path/to/lean --output /tmp/authrefine-lean
```

The runner checks `proofs/*.lean` and `source_study/proofs/*.lean`, records
compiler output and rejects a nonzero exit, timeout, changed source or `sorry`
warning. The retained thirteen-file compilation and statement outputs are in
`results/lean/`. Each file's printed axiom dependencies are preserved; the
recorded compilation reports no `sorryAx` dependency.

| File | What its checked statements establish |
|---|---|
| `BindingDiagnosis.lean` | Matching prefixes and a shortest fixed-binding witness from a valid rank bound and shallower local agreement. |
| `CachedFactory.lean` | Protocol-relative correspondence and the stated six-state component-table obligations. |
| `ClaimRoleObservation.lean` | Membership observations stabilize after the first repeated append, although raw lists can change. |
| `EpochCache.lean` | Cache transparency under an immutable epoch-to-payload mapping and valid cached entries. |
| `NativeConversion.lean` | Deny-overrides conversion, conditional trace lifting, and sequential composition. |
| `OutcomeObservation.lean` | Fixed-length Boolean-vector packing is injective and can distinguish denial from error. |
| `ProtocolDiagnosis.lean` | Protocol-relative local/trace equivalence, a shortest admitted witness, the reachable target/caller bound proved by cycle deletion and finite counting, initial disagreement, and reachable-configuration trace lifting. |
| `RelationalProjection.lean` | The two admitted field projections preserve their typed membership/permission events. |
| `source_study/proofs/ActiveOrganizationOrder.lean` | Ordering of invalid/missing/selected organization inputs and the declared superuser bypass. |
| `source_study/proofs/ClosureGuardComposition.lean` | Disjunction over captured role/permission requirements and iteration over supplied tenant gates. |
| `source_study/proofs/DRFDynamicFactory.lean` | The stated authentication, membership and ownership conditions of the selected predicate. |
| `source_study/proofs/DRFGuardComposition.lean` | The stated DRF permission-composition implications and rejection of cross-branch authorization. |
| `source_study/proofs/OrganizationQueryGate.lean` | Selected-row/first-row agreement with the relational contract under the queried-pair uniqueness premise. |


## Complete profiles

| Question | Driver | Retained data |
|---|---|---|
| Direct semantics and total-table groups | `audit_support_indexed.py` | `results/support-indexed/` |
| Overlapping support and correlated subfamilies | `audit_support_overlap.py` | `results/support-overlap/` |
| Partial target and ungrouped caller families | `protocol_family_audit.py` | `results/caller-family/` |
| Active grouping with caller history | `audit_protocol_grouping.py` | `results/protocol-grouping/` |
| Fixed-binding caller characterization | `protocol_audit.py` | `results/protocol-audit.json` |
| Session distinguishability and minimum short-test coverage | `audit_session_distinguishability.py` | `results/session-distinguishability/` |
| Session request and fresh-store costs with correct anchors | `audit_session_operation_cost.py` | `results/session-operation-cost/` |

Run a driver from `artifact/` with `proofs/` before its filename and a fresh
`--output` path. All listed drivers except the fixed-binding audit
produce directories; the fixed-binding audit produces a JSON file. Each
document beside its driver defines the domain,
independence of its oracle, denominator and sensitivity controls.

The overlap domain has four states, four requests and recurring supports
`{x,y}`, `{y,z}` and `{z,x}`. Checking all nonempty subfamilies tests active
membership retirement and correlations. The caller-grouping extension adds
six caller languages, all single-cell changes and every one-cell omission.
Its independent admission closure and explicit source/target/caller search
check all 123,930 family cases, including every replay field. Those cases reuse
2,904 distinct admitted target/caller/binding oracle answers across subfamilies.

The separate one-request family domain and the 1,679,616 fixed-binding
reference/target/caller triples exercise different obligations and retain
separate counts. A repeated independent computation is evidence of
implementation agreement on its declared inputs, not another application
sample. The paper uses native source experiments for the application connection
and equal-output measurements for computational cost.

## Session costs from complete and partial stores

[session-operation-cost.md](session-operation-cost.md) proves the request
cost from a complete store, including correctly supplied anchors, adaptive
request choices and resets. It separately gives the number of fresh-store
words required by the one-removal caller under decision/presence observation.
[session-initial-state.md](session-initial-state.md) extends the result to
every supplied initial row subset. It distinguishes complete restoration from
resetting to the same initial subset, derives the exact remaining request and
fixture costs, and characterizes the surviving families over complete request
languages.

Run the retained independent audits and native-history reconciliation from
`artifact/`:

```sh
python -B -W error proofs/audit_session_operation_cost.py --verify-retained results/session-operation-cost
python -B -W error benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
python -B -W error source_study/session_initial_state/run.py verify --input results/session-initial-state
```

The initial-state finite audit combines optimal belief-state searches with
complete-language products across supplied anchor and initial-state contexts.
The separate native study retains complete executed words and fixture
reconstruction records. Its independent oracle evaluates each supplied fixed
binding through the entire recorded history. The
[study guide](../source_study/session_initial_state/README.md) gives the
acquisition commands; the
[evidence guide](../results/session-initial-state/README.md) separates
production requests, complete restorations, resets and fixed-binding
comparison counts.

## Observation and process-record admission

These retained checks validate complete declared domains, typed fields and
derived reports. Entry paths are relative to `artifact/`.

| Evidence | Read-only entry | Retained records |
|---|---|---|
| Credential observation and serializer type controls | `benchmarks/audit_credential_admission.py --mode check` | `results/credential-admission-review/` |
| Complete source-body observations and executable controls | `-m source_study.verify_source_observer` | `results/source-observer/` |
| Six-method worker records, complete profiles and timing summaries | `benchmarks/audit_symbolic_comparison.py --verify-review results/symbolic-comparison-review` | `results/symbolic-comparison-review/` |

Prefix each entry with `python -B -W error`. The credential check validates
the retained native baseline and exact serializer faults without importing
Django. The source-body verifier reexecutes the selected CPython functions on
owned SQLite records, then reproduces the production comparison and all eight
source controls. Its
[observer guide](../source_study/independent_observer/README.md) specifies the
compared fields and complete fixture/graph admission. The six-method auditor
reconciles retained process and profile evidence without executing a timing
campaign; [symbolic-comparison-review.md](symbolic-comparison-review.md)
defines that evidence contract and its malformed-record controls.

## Native API observation review

`audit_native_healthchecks.py` independently reconciles the retained native
HTTP evidence, actual source controls, physical SQLite files, complete
configuration profiles and fresh prefix replays. It also checks seven observer
sensitivity controls and first-difference placement at every one of the 37
event positions. These latter checks alter retained observations and add no
native application executions.

```sh
python3 -B proofs/audit_native_healthchecks.py --results results/native-healthchecks
```

The default is read-only. To retain another review, add `--output` with a new
directory outside the scientific results being checked. The recorded review
is in `results/native-healthchecks-review/`; `native-healthchecks-review.md`
describes the observer defects closed by these checks and the exact scope of
the finite prefix comparison.
