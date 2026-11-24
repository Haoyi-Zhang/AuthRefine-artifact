# Native session lifecycle and observation depth

This experiment connects actual session-store operations to finite, fixed-binding
diagnosis. It executes the bundled complete `SessionsBase` module from Piccolo API,
calls its original `get_user_id` and
`remove_session` methods, and persists their effects through Piccolo 1.16.0 and
SQLite. A second execution interprets the complete selected method bodies with
AuthRefine's existing `EffectInterpreter` and an independently implemented
in-memory query/store provider.

The retained result is `results/native-session/`. It includes separate native
and interpreted records, the richer-identity comparison, complete-family
diagnoses and fresh native witness executions. The dependency gate identifies
the actual installed source used for acquisition.

## Reproduction

From the artifact directory, create a private environment and install the shared
native dependency lock:

```sh
python3 -m venv /fresh/authrefine-native
/fresh/authrefine-native/bin/python -m pip install -r source_study/historical_h19/requirements.lock
/fresh/authrefine-native/bin/python -B source_study/stateful_sequence/run.py --output /fresh/session-results
/fresh/authrefine-native/bin/python -B -W error -m unittest discover -s tests -p test_stateful_sequence.py -v
```

The output directory must be new. The driver checks the original module hash,
the native package versions and 411 distributed Python dependency-file hashes.
It saves native observations before importing the production interpreter or
finite checker. A failure leaves the completed records and traceback in place.
Eleven focused tests pass in the native environment. Without Piccolo, eight
tests run and three native tests are explicitly skipped; that partial run is not
evidence of native replay.

## Boundary and records

The original module imports and model class initialization execute. The two
selected async method bodies retain their original queries, control flow and
awaits. A fixed `datetime.now()` provider returns `2020-01-01T00:00:00` so strict
expiry comparisons are repeatable. Database records, tokens and user identifiers
are public fixtures. No account, network service, HTTP endpoint or historical
application is contacted.

The second arm supplies typed query capabilities and integer-second timestamps
to the existing bounded interpreter. Its small profile adapter handles the
source's `cast`, timestamp addition/subtraction and token-column equality; it
does not invoke native ORM objects, SQLite, or the native observer. This adapter
is newly written source integration, not a frozen front-end transfer result.

Each operation records the exact token argument, returned user id, selected
record identity, complete before/after persisted rows, removed row ids, and the
two-bit row-presence encoding. The native selected record is read from the
actual method's local variable with a Python tracing hook; the source body is
unchanged. The presence projection is admitted only after checking that every
remaining row equals its initial record. Expiry-renewal inputs are a separate
comparison grid and are not placed in that two-bit lifecycle model.

| Comparison domain | Paired observations | What it establishes |
|---|---:|---|
| Unmodified lifecycle graph | 40 | All 4 reachable presence states and all 10 requests; persisted deletion and independent session isolation |
| Unmodified expiry grid | 90 | Missing tokens, strict soft/hard expiry boundaries, optional renewal, and saved expiry values |
| Introduced omitted-delete control | 10 | All requests at its single reachable state; a completed removal without persistence |

The 130 unmodified observations and 10 control observations all agree between
the native and interpreted arms. The graph runs execute 40 additional prefix
operations per arm to establish their starting stores. Prefixes are not counted
as additional paired cases. Six diagnostic witnesses are then executed again in
the native source, using 10 further operations. Acquisition totals are therefore
180 source-method calls per arm, plus 10 native witness calls.

## Supplied correspondence contract

Two live sessions belong to the same user, as with two devices signed into one
account. The removal operation receives an already resolved session-store label,
`row-a` or `row-b`. Authentication receives a presented credential label,
`credential-a` or `credential-b`. Fixtures specify the exact token strings
actually passed to the source. The reference review supplies two possible
bijections from credential labels to independently named rows: identity and
swap. The removal-side row naming stays fixed under both hypotheses.

This is an explicit integration-review question, not an assertion that the
upstream source or business requirements are ambiguous. Both hypotheses agree
on every request from the initial store under the declared decision/presence
observation. Removing row A leaves the same persisted state under both; the next
authentication of credential A distinguishes their interpretations. The native
source returns no user, while the swapped reference still points to live row B.

Ordinary and support-indexed binding diagnosis, a shared target/caller graph, and an independently
implemented product search over direct contract equations all retain the
identity mapping and exclude the swapped mapping with the same two-step minimum:

```text
remove(row-a); lookup(credential-a)
```

All 11 shorter words (the empty word and 10 single requests) agree. A caller
allowing arbitrary lookups and at most one removal gives the same result; it
allows lookups from the start and does not force the two-step witness.

The selected row identity is also available in the raw observer. If it is added
to the reference observation, the swapped mapping is distinguishable on the
first lookup. The two-step result therefore demonstrates the horizon for the
stated decision/presence contract. It does not claim that two requests are
necessary when the reviewer compares richer identity fields.

The finite decision label has an explicit entry-level meaning: a lookup allows
when it returns a user id and denies when it returns `None`; a normally completed
removal allows, including deletion of an absent token. It does not assert that
an arbitrary caller is authorized to invoke the session-store removal helper.

## State-observation ablation

One in-memory source edit replaces the awaited delete in `remove_session` with
`return None`. Its AST and original source hashes are retained. Original source
files are never modified. The edited helper returns the same value as the
unmodified helper, but leaves the session in SQLite.

| Observation/check | Unmodified source, swapped mapping | Omitted delete, either mapping |
|---|---:|---:|
| Every initial one-step decision | No distinction | No distinction |
| Exact decision-only product search | Shortest difference: 2 | Shortest difference: 2 |
| Complete declared presence state plus decision | Shortest difference: 2 | Shortest difference: 1 |
| Selected record identity added | Shortest difference: 1 | State still distinguishes at removal |

For the omitted delete, a full-state check identifies the faulty transition as
soon as removal completes. A decision-only product check finds the later
authentication difference. This compares observation information as well as
search; it is not a claim that decision-only product search is unsound. The
control is one introduced fault, not a newly discovered Piccolo vulnerability.

## Files and scope

`fixtures.json` supplies the complete input domain. `native-observations.json`
and `interpreted-observations.json` retain separate values and graph prefixes.
`diagnosis.json` includes the policy, explicit two-member family, caller
protocols, oracle results, shortest witnesses and replays.
`native-witness-replay.json` contains fresh execution of those witnesses.
`native-dependencies.json` identifies the real runtime files; `runtime.json`
records local source and output hashes. Runtime seconds describe validation,
not an end-to-end performance comparison with older experiments.

This is one additional runnable source application relative to the original
Healthchecks/Pretix/Wger observer. It is the same Piccolo source family used by
the separate H19 historical-boundary replay, so those two experiments are not
two independent applications. The lifecycle run does not re-create the H19
historical vulnerability or its installed application environment. This lifecycle
study uses a sequential model, a fixed clock and two sessions. The separate
[session correspondence study](../session_correspondence/README.md) extends
the actual native acquisition to two through six sessions and all corresponding
bijections, including restricted callers and anchored candidate families.
Neither experiment models concurrent database operations or HTTP middleware.
