# Independent execution of selected source functions

This experiment supplies a runnable source observer and its explicit fixtures.
It executes the control flow of thirteen selected, hash-pinned function
definitions in CPython, records their concrete boundary values, then compares
them with fresh executions of the production AST interpreters. Its source
functions belong to the same three applications already in the study.

From the artifact root, use a new output directory:

```sh
python -B source_study/independent_observer/run.py --output /fresh/independent-observer
```

The command needs only the Python standard library. It refuses to overwrite
an existing output directory. Raw fixture and CPython observation files are
written before the production comparison modules are imported. A failed run
retains its written evidence and a traceback.

To check the included acquisition and its targeted tests:

```sh
python -B -W error -m source_study.verify_source_observer --results results/source-observer
python -B -W error -m unittest tests.test_independent_source_observer tests.test_observation_evidence -v
```

The verifier preserves all seven retained files. It reexecutes the selected
CPython functions, the production comparison and all eight source controls,
then checks the complete summary and recorded code identities. Supply the new
acquisition directory to `--results` to check a fresh run. An optional
`--output` receipt must name a new file outside the acquisition directory.

## Source and execution boundary

`source.py` verifies the complete original module identities before selecting
functions. It reads Healthchecks and Pretix from the distributed source files,
and Wger from the existing licensed source packet. Module imports, model class
initialization and framework dispatch do not execute. Function decorators and
annotations are removed without evaluation; the complete function bodies and
Python control flow are retained. The Healthchecks entry functions are then
explicitly composed with their selected original authorization closures.
The outer POST/CORS/CSRF middleware is outside the resume boundary.

`observer.py` provides fixed owned query, response and serializer-boundary
contracts, with SQLite storage for Healthchecks records/events and Wger inserts.
MAC comparisons use the standard-library HMAC implementation and a public
fixture secret. These functions do not connect to an application or account.
This fixed experiment accepts no source-file path supplied at the command line;
it is not an arbitrary-Python sandbox. The existing Django/bubblewrap replay
and its isolation gate are neither invoked nor modified.

| Profile | Freshly executed domain | Compared observation |
|---|---:|---|
| Healthchecks read | 480 inputs | Status, resolved project and identity, readonly/version, manager return, serializer arguments and effect order |
| Healthchecks resume | 448 reachable edges: 8 states × 28 symbols × 2 credential forms | Every read field plus before/after state, all three persisted records, events, event delta, store invariant and prefix observations |
| Pretix active team-token/event | 288 inputs | Permission decision, selected event and its identity, organizer, complete supplied grant set |
| Wger guarded owner insert | 16 inputs | Guard decision, persisted rows, number of saves and exact request-user identity |

The read grid includes 240 body-only GET requests. The source read wrapper uses
headers, so these all stop before credential lookup. Of all 480 reads, 36 return
200, 72 return 403, 36 return 404 and 336 return 401. The remaining cases cover
plain/stored-MAC keys, write/read credentials, missing/malformed/unrecognized
keys, a nonmatching same-prefix MAC, all three API versions and owned, foreign
and absent objects. Prefix collisions between the first two owned projects
exercise full digest selection rather than prefix-only lookup.

The resume graph reaches each store state by executing a successful prefix from
the initial store. It then carries that store into the measured request. The
448 measured edges require a further 672 prefix-step executions. Status counts
are 24 successful updates, 24 repeat conflicts, 96 ownership denials, 48 missing
objects and 256 credential denials. Every successful update inserts one event,
clears the selected timing fields and leaves the other two records unchanged.
The projection to three resumed bits is admitted only after checking the full
record/event invariant. Prefix executions are not additional independent cases.

## Independence of the comparison

`fixtures.py` and the CPython collector import no production evaluator or saved
outcomes. `compare.py` imports the production implementations only after the
raw observations have been saved. Healthchecks uses the existing credential
and selected-body interpreters with a separately implemented in-memory provider.
Its typed records, query selection, save/event operations and observation
collection do not call or inherit the CPython collector, which uses SQLite.
The two implementations share the declared finite primitive contracts and
input rows. This cross-checks source control flow, argument propagation and the
two owned provider implementations; it does not establish that the supplied
contracts describe a complete Django deployment. Pretix and Wger use their
existing separately implemented providers.

Pretix's raw query filters and access/grant argument identities are also recorded
by the CPython collector. The fresh cross-arm comparison covers the five fields
listed above, because the production profile does not export all those extra
handoff fields. The exact compared-field list is stored in `summary.json`.

The raw resume graph is passed to a separately declared three-bit policy with
27 fixed owner bindings for each credential form. The family diagnosis retains
one matching binding and gives a one-step witness for each of the other 26.
All 52 witnesses are executed again in the CPython collector. The source fixture
alphabet and the checker's canonical alphabet have an explicit checked mapping;
their ordering is not assumed to coincide.

`evidence.py` admits complete ordered fixture IDs and every declared
state/input edge before comparison. It checks each recorded prefix against
the complete graph and requires it to establish the edge's stated source
state. `compare.py` requires both value and type equality for observation
fields and serializer transfers. The retained verifier checks the complete
freshly recomputed comparison, including its Boolean agreement fields. The
selected source language retains Python's ordinary equality semantics.

## Executable source controls

Eight controls change one selected executable source site each: serializer
version, checked-versus-serialized object, omitted save, duplicate event,
uncleared timing field, wrong organizer, omitted grants and client-supplied
owner. Original source files stay unchanged. Each control has original and
modified AST hashes. For a stateful edge, an unmodified prefix establishes the
starting store before the modified final operation executes.

Across 2,896 control/input executions, the changed source produces 318 distinct
baseline/control observation differences: 24 change the HTTP status code
(Healthchecks) or entry permission decision (Pretix/Wger), and 294 preserve
that coarse outcome while changing another recorded field. The status-only
comparison does not compare complete HTTP response bodies. These are
controlled executions of eight introduced faults, not discovered upstream
defects or an estimated field-error detection rate. Full baseline and modified
observations are retained for every changed case; unchanged-case counts are
reported for each control.

## Relation to earlier observations

The 1,232 new comparisons have zero disagreements in the completed run. They
are new fixtures and a new runnable observer, not a reconstruction of the
historical 272 equality-coded comparison records. Those original records remain
unchanged. Wger's original date-validation serializer and its raw date fixtures
are absent from the distributed sources; the new Wger experiment covers the
guard-to-owner insert boundary only. It does not reproduce the earlier eight
date trials or establish full serializer validation.

The complete source files and their original licenses stay in their existing
locations: Healthchecks BSD license, Pretix AGPL with its additional terms, and
Wger AGPL in `adaptation_study/sources.json.gz`. The optional in-memory source
mutations are identified as modifications made on 2026-11-18 and retain the
terms of the original source from which they are derived.

## Retained execution records

`results/source-observer/` contains the source observations, complete paired
comparisons, source-control observations and execution record. Its observer
uses the independent in-memory provider described above. The explicit bijection
in `compare.py` maps source-fixture order to canonical checker order and is
covered by a regression test.

`runtime.json` identifies the observer and imported checker files used for
the recorded execution. Its wall times describe reconstruction on this machine;
they are not a comparison with the separate native Django experiment.
The execution tests in `test_independent_source_observer.py` cover
source-identity rejection, complete-body extraction, credential-prefix
selection, early rejection, unchanged denials, state persistence, executable
mutation effects and canonical graph/witness indexing. The admission and
reconciliation tests in `test_observation_evidence.py` also check complete
fixture and edge domains, prefix consistency, Boolean/integer distinctions,
serializer handoffs, dependency identities and source-control totals.
