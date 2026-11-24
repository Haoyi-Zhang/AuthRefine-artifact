# Native Conet policy-store diagnosis

This study executes the complete distributed Conet `PolicyEngine` module with
the real Casbin FileAdapter. It follows changes from the method return through
the current rule set and the policy file into a newly constructed instance.
The original implementation enables auto-save, but successful rule mutations
leave its file unchanged in the retained native dependency configuration. A
separately executed source repair saves the complete policy after a successful
mutation. Both arms are checked against the same durable-store contract.

The experiment extends the existing Conet case. It adds a second application
implementation to the complete-module stateful execution evidence; it does not
increase the number of projects in the source study. The three owned ACL rows
are the inputs already used by `source_study/repair_profiles.py`.

## Source, dependencies and executable repair

The original module and adjacent Casbin model are
`source_study/source/repair-profiles/conet/src/conet/control/policy.py` and
`policy_model.conf`. Their source identity, original package declaration,
Apache license and NOTICE are checked against the distributed source binding
before import. The module is imported intact, including its real `jose`
dependency. No import or native method is replaced by a fixture implementation.

The collector calls `PolicyEngine.add_policy_rule`, `remove_policy_rule`,
`list_policy_rules` and the original asynchronous `authorize` method. A restart
constructs a fresh `PolicyEngine` against the same owned file. The constructor
and these methods run as Python code from the complete module. JWT creation and
verification methods are present in that import but are not part of the
measured operation interface.

Add, remove and authorize return native Booleans. The restart symbol records
successful construction as an allowed interface event and records the actual
returned instance type separately; construction is not a Boolean-returning API.

`native.py` constructs the repair independently of the existing source lowerer.
Each of the two direct mutation returns becomes:

```python
changed = self._enforcer.add_policy(subject, skill_id, action)
if changed is True:
    self._enforcer.save_policy()
return changed
```

The removal method receives the corresponding change. The complete derived
module is then imported and executed; no external save flag selects the result.
The exact executed candidate, original model, license and NOTICE are retained
under `results/native-policy-store/source-candidate/`. The original module
remains unchanged.

`requirements.lock` pins the actual dependencies used for this experiment,
including the imports required by the complete source module.
`native-dependencies.json` records the installed distributions and their
integrity evidence; their installed file contents are checked against the
distribution records before collection. The selected versions satisfy the source package's Casbin
and python-jose dependency ranges. This is a sequential owned-file experiment;
it does not launch the Conet service or test who may administer its policies.

## Reachable states and review correspondences

The supplied universe contains these exact request tuples:

| Row | Subject | Skill | Action |
| --- | --- | --- | --- |
| 1 | finance | invoice.verify | invoke |
| 2 | marketing | research.find_leads | invoke |
| 3 | marketing | invoice.verify | invoke |

All eight subsets are used as initial policy files in each arm. The request
alphabet has twelve symbols: add, authorize, remove and restart at each row
label. Restart uses the same file regardless of the label; these three symbols
retain the existing finite interface rather than representing three restart
implementations.

Each review family contains the six bijections from reference row slots to
these request labels. One correspondence is shared by add, remove and authorize
and remains fixed throughout every execution. The six bijections are supplied
review hypotheses; the collector does not infer ambiguous deployed
configuration from these inputs. Independent choices that would map several
slots to the same request are absent from the family.

The observation has six membership bits: three for the disk policy and three
for the current instance. The native target retains more information: exact
ordered memory rows, exact ordered file rows and the file text. In particular,
the six possible orders of a full three-row policy remain distinct target
states. The collector reaches each target state by executing its recorded
prefix from the initial file, then executes every declared next request. It
does not populate an arbitrary intermediate memory/disk pair directly.

Each of the sixteen cases reaches sixteen physical states with eight distinct
membership observations and 192 measured state/request cells. All orders
receive their own measured outgoing operations. The verifier additionally checks that physical states with the
same membership observation have the same decision and successor membership
for every request.

| Recorded unit | Count |
| --- | ---: |
| Initial-file/arm cases | 16 |
| Native measured edges | 3,072 |
| Additional actual reaching-prefix operations | 7,440 |
| Distinct original physical-state/request pairs across initial files | 1,536 |
| Distinct repaired physical-state/request pairs across initial files | 192 |
| Distinct original membership/request pairs | 768 |
| Distinct repaired membership/request pairs | 96 |

The repaired graph is reachable from every initial file, so many of its edges
are measured again from a different reaching history. The table separates those
executions from distinct states and cells. Constructor and observation calls
are retained separately from measured and prefix operations.

The actual native edges also connect to the earlier source-lowered Conet table
in `source_study/data/repair-profiles.json.gz`. An explicit map relates its
`permission_0..2` labels and `disk_0..2,memory_0..2` bits to the new row labels
and membership observations. The three tuple identities are checked against
the earlier input declaration. All 768 original membership/request cells have
matching actual native executions, reached through the eight initial files.
The repaired module reaches 96 of the earlier 768 cells, all matching; the
other 672 directly initialized old cells are outside this repaired closure.
`previous-table-comparison.json.gz` retains every distinct comparison, its
native-record location and its repetition count. This checks the earlier
lowering against complete-module execution without treating arbitrary old
intermediate-state setup as one reachable application history.

## Complete diagnosis and actual replay

The durable reference is a direct set contract. A successful mutation changes
the current set and persists that complete set; an unchanged add or remove
leaves both stores unchanged; authorization queries the current set; restart
loads the disk set. `oracle.py` implements these equations and an independent
reference/target/caller search without importing the production evaluator,
compiler, support analysis, source lowerer or profile traversal.

Four total-table algorithms and scan/grouped analysis under four callers are
compared with that independent result. The callers permit unrestricted
operations, authorization queries only, at most one mutation, or one mutation
followed by restart and authorization queries. Every compared result includes
all supplied bindings, exact shortest word indices and full fixed-binding
replays. The 1,152 method/binding comparisons repeat the same sixteen native
cases and are not independent source samples.

The original module has no matching correspondence under any caller that
permits mutation. The executed repair has exactly one matching correspondence,
the identity, for all eight initial files under those callers. Authorization
queries alone retain all six bijections for the empty and full initial sets,
and two bijections for each other initial set. The complete profile therefore
distinguishes insufficient observations from a persistent-store discrepancy
and from an incorrect row correspondence.

With the complete membership observation, the original implementation's first
successful mutation already differs from the durable contract: its memory
changes while its disk does not. The shortest identity-binding witness has
length one. The repair's other five correspondences also have one-request
witnesses under a mutating caller.

A separate experiment withholds the store observation and compares only API
Booleans. Its independent product search retains the internal states needed to
predict future behavior, but compares only the returned value. This experiment
does not use the full-observation diagnosis theorem. For the identity binding,
the shortest original-source difference now has length three. From the empty
file, canonical unrestricted order selects `add, restart, add`: the final
add's return value exposes the lost change. Under the explicit
mutation/restart/query caller, the shortest word is
`add, restart, authorize`, so the original authorization consumer itself
exposes the lost policy. Both forms are actually replayed against source
instances and files. The repaired implementation matches the Boolean-only
contract under the identity binding, while initial-set-preserving renamings
remain observationally
indistinguishable when row identity is withheld.

The retained native replay executes 69 distinct case/word pairs comprising 101
request operations. Those physical records are checked against 544 excluded
binding/contract entries from five full-observation profiles and two
Boolean-only profiles. Algorithm duplicates are not replayed and counted again.
These are canonical witness groups, not an optimal test-suite claim.

## Reproduce and inspect

From the artifact root, install the lock into an isolated Python environment:

```sh
python -m pip install -r source_study/native_policy_store/requirements.lock
python -B source_study/native_policy_store/run.py acquire --output /fresh/conet-store
python -B source_study/native_policy_store/run.py analyze --output /fresh/conet-store
python -B source_study/native_policy_store/run.py replay --output /fresh/conet-store
python -B source_study/native_policy_store/run.py verify --output /fresh/conet-store
python -B -OO source_study/native_policy_store/run.py verify --output /fresh/conet-store
python -B -W error -m unittest tests.test_native_policy_store -v
```

Acquisition requires a new output directory. Raw source observations are written
before any production policy evaluation. Analysis and replay read those frozen
records, and the read-only verifier reconstructs every rich edge, prefix,
complete profile, shortest word and source replay from its underlying records.
The test suite checks actual original/repaired execution and rejects changed
source, missing prefixes, corrupted disk/replay records, illegal family members
and conflated full-observation/Boolean-only witness lengths. The native replay
verifier also binds every recorded request to its declared word index and
checks complete store continuity between consecutive records. The three native
tests require the supplied lock; twelve contract/record tests also run without the
native dependencies.

| Evidence | Retained file |
| --- | --- |
| Source inputs and fixed families | `fixtures.json` |
| Complete native states, prefixes and edge observations | `native-observations.json.gz` |
| Checker inputs and independently checked complete expected profiles | `inputs.json.gz` |
| Independent full and Boolean-only profiles | `profiles.json.gz` |
| Case counts and algorithm work | `diagnosis.json`, `case-summary.csv` |
| Native shortest-word requests and actual records | `native-replay-inputs.json.gz`, `native-witness-replay.json.gz` |
| Complete-module/native connection to the earlier source-lowered table | `previous-table-comparison.json.gz` |
| Replay totals and read-only validation | `native-replay-summary.json`, `validation.json` |
| Executed source/dependency identity and acquisition scope | `source-identity.json`, `native-dependencies.json`, `acquisition.json` |

The records are under `results/native-policy-store/`. Acquisition wall times
cover file setup, source execution, reaching prefixes, observations and target
construction. Common source/dependency checks, module imports and output
serialization lie outside those per-case clocks. These acquisition times are
not diagnostic-algorithm timings. `inputs.json.gz` exposes each case's policy,
target, fixed family, callers and full expected profiles for a separate
same-input algorithm comparison.
