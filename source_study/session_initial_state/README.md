# Session correspondence from a partial initial store

This study asks how an already supplied presence state changes the requests
needed to certify a fixed row-to-credential correspondence. It uses the same
selected session source and native adapter as the session-correspondence
study. Every retained word is executed from its own freshly prepared initial
fixture, including any reconstruction steps inside the word.

For `m` unanchored rows, let `d` be initially absent and `p=m-d` initially
present. With decision/presence observation, the exact request optimum is
`2(m-1)-1` for a mixed initial store and `2(m-1)` otherwise. Selected-row
observation needs `m-1` requests. These expressions apply when `m>=2`; the
family is already a singleton when `m<=1`. Both observations require one
complete restoration exactly when `d>=2`, and the request and restoration
minima are attained together. A restoration cost `rho>=0` therefore adds
`rho` precisely in that case. The proof covers arbitrary correctly anchored
rows, initial stores and adaptive strategies.

`restore_complete` recreates all original rows and credentials. `reset_initial`
recreates only the supplied initial subset. Both are explicit harness fixture
operations, separate from production lookup/removal requests, and preserve the
same candidate and all earlier observations. Over the complete admitted request
language, and without complete restoration, lookup-only projected observations
leave `p!d!` members; permitting removals or observing selected row identity
leaves `d!`. When two free rows
are initially absent, repeated `reset_initial` cannot certify identity.

## Files and independence

| File | Responsibility |
|---|---|
| `strategies.py` | Predeclares optimal words and reset controls, before acquisition. |
| `collector.py` | Calls the actual selected session methods through the existing native Sessions adapter and records complete physical histories. |
| `oracle.py` | Independently evaluates a fixed row-to-credential permutation through a supplied initial state and the entire recorded history. |
| `validation.py` | Checks exact input coverage, native field values, all legal bindings, operation counts and retained reports. |
| `provenance.py` | Captures execution and verification code identities; reconciles source, dependency and evidence identities without loading native dependencies. |
| `run.py` | Separates fresh acquisition from read-only verification. |
| `benchmarks/audit_session_initial_state.py` | Independently searches finite belief states and exhausts exact surviving families; imports none of the study modules. |

The collector imports neither the oracle nor a production diagnosis method.
The oracle imports neither the collector nor the word constructor. It uses
`binding[row-1] = credential`, so lookup of credential `j` selects the inverse
image of `j`. Full physical rows and tokens validate execution. Candidate
comparison uses only the declared decision/presence observation, adding only
the selected row identity in the richer mode.

## Read-only reproduction

Run these commands from `artifact` with Python's standard library:

```sh
python -B -W error source_study/session_initial_state/run.py verify --input results/session-initial-state
python -B -W error benchmarks/audit_session_initial_state.py --verify results/session-initial-state/finite-audit.json.gz
python -B -W error -m unittest discover -s tests -p test_session_initial_state.py -v
```

Verification compares every scientific field of the retained validation report
and finite audit. It rejects duplicate JSON keys, nonfinite values, Boolean
values in integer fields, changed caller/observation contracts, missing or
altered native events, changed reconstruction semantics and mismatched content
identities. The same checks run with `-OO`; they do not depend on `assert`.

## Fresh native execution

Install the existing native dependency lock in a dedicated environment:

```sh
python3 -m venv /fresh/authrefine-native
/fresh/authrefine-native/bin/python -m pip install -r source_study/historical_h19/requirements.lock
/fresh/authrefine-native/bin/python -B -W error source_study/session_initial_state/run.py acquire --output /fresh/initial-store-results
python -B -W error source_study/session_initial_state/run.py verify --input /fresh/initial-store-results --report /fresh/initial-store-results/validation.json.gz
python -B -W error benchmarks/audit_session_initial_state.py --output /fresh/initial-store-results/finite-audit.json.gz
```

The acquisition command rejects any existing destination before loading the
source or dependencies. Verification never rewrites evidence; `--report` also
requires a fresh file. If an interrupted acquisition leaves a partial
directory, retain it as incomplete evidence and select a different fresh
destination. Execution and verification source contents are frozen in the
acquisition receipt. A source change requires a fresh acquisition to produce
a matching receipt.

The native dependency gate checks the admitted native package files and
versions. The receipt also retains the actual distribution inventory and
checks every package in the supplied lock. The recorded source manifests
come from the five actual Sessions instances used for acquisition. Start and
finish instants use the host UTC clock; session expiry uses the separate fixed
experiment clock. Acquisition duration is not reported as an algorithm timing
comparison.

## Evidence scope

The retained cohort comprises 248 optimal words from all 124 initial subsets
at two through six rows, under both observations, plus 10 reset-to-initial
controls. It contains 1,594 production requests in total and 218 separately
counted fixture reconstructions. These are tasks on one existing source
interface. Correctly anchored families and arbitrary cardinalities are covered
by the proof; the independent finite audit exhausts all anchor subsets and
initial stores through six rows.

See `proofs/session-initial-state.md` for the full proof and
`results/session-initial-state/README.md` for the exact result accounting.
