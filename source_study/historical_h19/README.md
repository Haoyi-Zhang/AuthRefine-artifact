# Native H19 producer, query and filter comparison

This experiment follows the existing pinned Piccolo source pair through real
column construction, the native ORM, SQLite, Pydantic model construction and
the complete `PiccoloCRUD.get_all` body. It uses two owned rows with fixed
fixture strings. It starts no HTTP server and makes no account requests.

## Research question

Does the historical secrecy change reach both consumers of the session-token
column: output selection and filter-model construction? A status-only check
cannot answer this question. A check of JSON field names is also insufficient:
the patched default response retains `token: null` while omitting the stored
token value from the query.

The public motivating case is
[GHSA-2gh4-jmwq-rr8w](https://github.com/advisories/GHSA-2gh4-jmwq-rr8w),
published by the project in June 2026. Its stated deployment preconditions and
impersonation chain are evidence from that advisory. This local experiment
checks the metadata/query/filter mechanism on owned data, not that chain.
Original API sources are already distributed, with their licenses, under
`../source/h19/`. The source commits are recorded in `pins.json`.

## Executed domain and independent comparison

The experiment compares Piccolo 1.16.0, the minimum version declared by the
patched API source, with Piccolo 1.34.0, the version recorded by the migration
in the [upstream patch](https://github.com/piccolo-orm/piccolo_api/commit/520ec2567ae1d2cc417c8c0d1ad0ddc05549a8a4). Both use Piccolo API 1.10.0 support modules. Complete pinned before/after
session-table and CRUD modules execute unchanged. The installed Python files in those two packages are checked before execution:
411 files for the minimum profile and 422 for the migration-version profile.
`pins.json` and `pins-1.34.json` record their identities. The two complete
environment locks differ only in the Piccolo version. Neither is a recovered
historical installation lock.

Five profiles distinguish two historical source pairs, two controlled
producer/consumer cross-combinations and one owned repair. Each runs 18
selection contexts: six requested-column sets and three exclusion settings
(default, explicit true, explicit false). Per ORM version, this gives 90 native metadata observations and 15 filter
requests: 105 complete `get_all` invocations. The combined version matrix has
180 metadata pairs and 210 invocations. Identical fixtures are reused across
versions; these counts are not independent applications.

The native records are written before importing the earlier source interpreter.
The latter independently evaluates four metadata observations for the same
contexts: token secrecy, registry membership, query projection and filter
fields. It binds the registry predicate to the packaged, hash-matched source of
each ORM version, then evaluates that predicate over its own typed records. It shares no native Piccolo objects, SQLite executor or Pydantic model
with the native path. Actual SQL outcomes, row values, JSON responses, schemas
and filter requests are additional native observations, not paired-IR claims.

## Results

All 180 metadata comparisons agree. The default-selection mechanism is:

| Producer | Consumer | Stored token in output (both ORMs) | Token filter, ORM 1.16 | Token filter, ORM 1.34 |
| --- | --- | --- | --- | --- |
| Before | Before | Present | Accepted | Accepted |
| After | Before | Absent | Accepted | Accepted |
| Before | After | Present | Accepted | Accepted |
| After | After | Absent | Accepted | Rejected |
| After | After with owned filter repair | Absent | Rejected | Rejected |

Both original default GET responses have status 200 and the same JSON field
names. The stored token value distinguishes them: before returns the fixture
value, while after returns null. This result is unchanged across the two ORMs.
The producer/consumer cross-combinations attribute output secrecy to the
producer declaration and the filter behavior to the complete handoff.

The native 1.16 registry classifies `Secret` subclasses; the patched producer
uses `Varchar(secret=True)`. Thus SQL reads the flag, but the filter consumer
receives an empty registry. Native 1.34 instead registers `column._meta.secret`.
The identical patched CRUD body then excludes the token from its real
Pydantic filter model and rejects both token-filter requests with status 400
before SQL. Across the 90 paired profile/context combinations, 54 registry observations
and 18 filter schemas change; query projections and selection responses remain
unchanged. Two of the 15 filter responses change. All installed package versions
apart from Piccolo are identical.

The owned filter-boundary adapter completes exclusions from native column
identity and secrecy metadata. It repairs the minimum-version filter contract,
is behaviorally redundant for the patched 1.34 profile, preserves the ordinary
`user_id` filter, and leaves output selection unchanged. This explains the
residual minimum-version result without implying that the upstream patch fails
under the version recorded by its migration. Only these two ORM versions were
executed; the experiment does not locate the first version with the changed
registry contract.

For each ORM, six of the 90 selection invocations raise a native SQLite `OperationalError`:
requesting only the token while exclusion is enabled leaves an empty SELECT.
They are retained as exceptions, not counted as successful HTTP responses.
Each version has 84 selection returns, six selection exceptions and 15 filter
returns; the matrix therefore contains 198 returns and 12 exceptions. The metadata-only interpreter predicts the empty projection but does
not execute SQL; its agreement cannot establish successful endpoint execution.
The filter repair addresses the filter boundary and retains this separate
empty-projection behavior.

## Reproduce

Use a fresh Python 3.12 environment. The 1.16 lock is shared with the separate
stateful session experiment; neither script installs or upgrades dependencies.

```sh
python3.12 -m venv /tmp/authrefine-h19-env
/tmp/authrefine-h19-env/bin/python -m pip install -r source_study/historical_h19/requirements.lock
/tmp/authrefine-h19-env/bin/python -B source_study/historical_h19/run.py --output /tmp/authrefine-h19-fresh/orm-1.16.0
python3.12 -m venv /tmp/authrefine-h19-134-env
/tmp/authrefine-h19-134-env/bin/python -m pip install -r source_study/historical_h19/requirements-1.34.lock
/tmp/authrefine-h19-134-env/bin/python -B source_study/historical_h19/run.py --orm-version 1.34.0 --output /tmp/authrefine-h19-fresh/orm-1.34.0
python -B -m source_study.historical_h19.matrix /tmp/authrefine-h19-fresh
python -B -m source_study.historical_h19.matrix results/published-patch
python -B -m unittest discover -s tests -p test_historical_h19.py
```

Run from `artifact/`. The output directory must not already exist. The offline
verifier uses only the standard library and independently recomputes the
fixture-level row/value and error expectations, grid coverage and agreement
counts. Tests deliberately corrupt saved observations and source bytes to
check that contradictory evidence is rejected.

`native-observations.json` contains the SQL, row values, serialized bodies and
schemas. `comparison.json` contains both metadata paths. `summary.json` states
the denominators; `runtime.json` records package versions and producer hashes.
`file-hashes.json` binds the exact saved outputs. Earlier minimum-only runs remain labeled by run number. The `matrix/` folder
contains the authoritative two-version comparison, with one subdirectory per
ORM and a reconciled matrix summary.

## Interpretation

The experiment establishes the behavior of the pinned source with the declared
native dependency profile. It gives executable evidence that output values,
filter admission and runtime exceptions are different observations. The
cross-version combinations and the metadata-completion adapter are controlled
experimental configurations, not released project versions. It neither
identifies the dependency versions of an affected deployment nor establishes
a new live vulnerability or a population detection rate.
