# Initial-state session evidence

The evidence connects the exact residual-cost theorem to complete native
execution from each supplied initial row subset. The physical source is the
unchanged selected session module already used by the session-correspondence
study. All reported native words were executed end to end through its native
ORM and SQLite operations.

## Native cohort

| Cohort | Complete words | Production requests | Complete restorations | Resets to initial store | Fixed-binding histories compared |
|---|---:|---:|---:|---:|---:|
| Optimal, decision/presence | 124 | 918 | 99 | 0 | 50,360 |
| Optimal, selected row | 124 | 516 | 99 | 0 | 50,360 |
| Reset-to-initial controls, both observations | 10 | 160 | 0 | 20 | 1,744 |
| Total | 258 | 1,594 | 198 | 20 | 102,464 |

The optimal cohort includes every initial subset at two through six rows, for
124 different supplied stores under each observation. All anchors are empty
in this native cohort. Every optimal word leaves exactly the identity binding
and attains both the predicted request count and the minimum number of
complete restorations. The independent oracle evaluates all 100,720
fixed-binding histories in this cohort through all recorded requests, for
692,432 comparisons, even after a binding has already disagreed.

Each reset control starts with the final two rows absent and performs two
actual resets to that same initial subset. Every control retains exactly
identity and the transposition of those absent rows. Its surviving family is
checked by member identity; no complete restoration is admitted in that caller.
The controls contribute 40,304 request comparisons over 1,744 fixed-binding
histories. The native total is therefore 732,736 request comparisons.

`restore_complete` and `reset_initial` are different fixture operations. They
are counted separately from production lookup/removal requests. Initial
fixture preparation is supplied before the residual experiment and is outside
the displayed operation cost. The complete physical records do not enlarge
the declared candidate-comparison observation: projected diagnosis uses only
decision and named row presence; the richer diagnosis also uses selected row
identity.

## Finite audit

The independent standard-library audit records 180 exact searches across all
initial subsets at one through four rows, both observations and three
reconstruction regimes. Those searches expand 57,609 belief states and inspect
290,536 transitions, without consulting the cost formula or construction.

Across all anchor subsets and initial stores at two through six rows, it
checks 5,456 contexts, 23,284 feasible constructions, 396,960 fixed-binding
construction histories and 9,452 impossibility contexts. The construction
histories use 2,033,832 request comparisons. Separate full-language products
check exact surviving families in 21,824 profiles, comprising 547,472
fixed-binding products, 864,098 visited product states and 3,796,745
transition comparisons. These finite checks are distinct from native source
execution and do not contribute to native sample or request counts.

## Retained files

| File | Contents |
|---|---|
| `inputs.json.gz` | Observation and reconstruction contracts; complete fixture rows; exact supplied bijections; every predeclared case and full word. |
| `native-traces.jsonl.gz` | One JSON record for each complete native word, with initial/final physical rows, all request records and both sides of every reconstruction. |
| `native-dependencies.json.gz` | Actual admitted package versions, dependency source identities and installed distribution inventory. |
| `source-execution.json` | Source manifest returned by each of the five actual native Sessions instances. |
| `acquisition.json` | Actual operation counts, UTC interval, runtime metadata and acquisition-time content identities for source, execution code, inputs and raw evidence. |
| `validation.json.gz` | Independently recomputed exact survivors and first disagreement for every supplied binding, together with case and cohort counts. |
| `finite-audit.json.gz` | Complete independent search results, construction contexts and surviving-family audit results. |

From `artifact`, run the following to reconcile every retained result without
altering the evidence:

```sh
python -B -W error source_study/session_initial_state/run.py verify --input results/session-initial-state
python -B -W error benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
```

The mathematical result and its assumptions appear in
`proofs/session-initial-state.md`; acquisition instructions appear in
`source_study/session_initial_state/README.md`. Local acquisition duration is
retained for reproducibility and is not an experimental speed comparison.
