# Native Healthchecks authorization and lifecycle study

This experiment follows API credentials through the original Healthchecks
project lookup, authorization decorators, API views, response serialization and
SQLite writes. The complete selected modules run under the pinned Django
runtime. The current source satisfies the declared interaction protocol under
its intended credential routing. Four source controls show how a response can
retain a successful HTTP status while losing its read-only context, or while
failing to persist a lifecycle change.

The study extends the existing Healthchecks source case. It contributes one
application implementation to the native execution evidence. API versions,
credential formats, source controls and routing configurations are experimental
conditions within that application.

## Public history and current executable source

The official Management API documentation defines project-specific API keys,
read-only and read-write access, and the response fields omitted from a read-only
reply. In the current API those fields are `uuid`, `ping_url`, `update_url`,
`pause_url`, `resume_url` and `channels`; a read-only reply includes `unique_key`.
The description field remains available.

Two public changes explain why this boundary matters:

* Pēteris Caune's 4 July 2019 change, “Don't include ping URLs in API responses
  when the read-only key is used,” adds read-only context in the decorators,
  passes it through a view, and uses it in the serializer. The upstream changelog
  lists it as an improvement. Its original response field set differs from the
  current API.
* Issue 346, reported by `jameskirsop` on 24 March 2020, describes a single-check
  GET that required a full-access key. Caune's fix that day separates the read
  handler from the write handler and forwards the read-only context. This is a
  documented over-rejection problem.

`source-evidence.json` retains the selected current source identities, both
complete commit patches and the issue text. `source-history-metadata.json`
records exact source URLs, authors, timestamps and reading scope. The current
source is distributed in `source/`, including its BSD license. These historical
records motivate the controls below; the executed controls are edits of the
current complete modules.

Primary sources:

* <https://healthchecks.io/docs/api/>
* <https://github.com/healthchecks/healthchecks/issues/346>
* <https://github.com/healthchecks/healthchecks/commit/1f1b1aedca949a52a592f8aefc523ad47b054ed9>
* <https://github.com/healthchecks/healthchecks/commit/76ae42bc8fe85ba8d12a24a842a08e17cf13682c>

## Executed boundary

The collector imports 27 original application modules from a 34-file retained
source closure. It executes the original `Project` and `Check` models,
`ProjectManager.for_api_key`, both authorization decorators, the API URLConf,
the complete views and their serializer. A real Django Client passes requests
through the native request-response pipeline, with CSRF checks enabled. Original
model classes create and query real SQLite rows. A separate `sqlite3` connection
reads committed rows after every operation.

The local configuration selects the accounts and API applications, authentic
Django middleware and the original API URLConf. It creates the current model
schema with Django's model synchronization and built-in auth migrations.
Application imports, model methods and query results are never replaced. The
native objects returned by `for_api_key` are observed with Python's profiling
callback; the callback records their identity without replacing the method.

The configuration runs the API boundary locally. Mail delivery, payments,
notification transports, deployment middleware and an upgrade through the
application's historical migrations are separate operations. The original
get-check, pause and resume test modules also run unchanged: 30 native tests.

## Source controls and fixed routing configurations

Each source arm imports its entire source closure. `run.py` constructs the
following exact edits in separate directories and retains their unified diffs
alongside the executed files.

| Arm | Exact change | Question answered |
| --- | --- | --- |
| `original` | Unchanged current source | Does the complete chain satisfy the supplied API/lifecycle contract? |
| `omit_readonly_context` | Omit the `readonly` argument in the three check-serialization calls | Can successful reads expose the write-capable response fields when view-to-serializer context is lost? |
| `wrong_project_context` | Replace both assignments of the resolved project by a real ORM query for the first project | Does the observer retain the actual manager object and project attribution? |
| `omit_pause_persistence` | Omit the pause handler's `Check.save` call | Can an in-memory response and Flip insertion conceal a missing Check update? |
| `reject_readonly_get` | Use the write-authorizing decorator on `get_check` | Does a valid read-only credential get rejected at the single-check route? |

The first and last controls isolate mechanisms present in the two public
changes. The other two are explicit research controls. Historical application
deployments are not executed in this study.

Four concrete credential-routing configurations are executed separately:
the intended routing, an exchange of read-only/read-write slots within each
project, an exchange of the two projects, and both exchanges together. The
selected configuration stays fixed throughout a run, including key rotations
and subsequent requests with the retired keys. Each configuration therefore
has its own executed target. These are concrete configuration contract checks,
not a correspondence family sharing one target.

The full grid contains five source arms, two initial credential formats
(legacy plaintext and native hashed keys), three API versions, and four routing
configurations: 120 cases, or 24 cases per source arm. The hashed credentials
are issued by the original native producer methods. Legacy credentials are
explicit initial records accepted by the native backward-compatible lookup.

## Protocol, reference equations and observations

`contracts.protocol()` declares one 37-operation word: 35 HTTP calls and two
native key rotations. It begins with same-project and foreign-project reads,
list and unique-key access, missing credentials and missing objects. It then
executes rejection checks, pause, repeated pause, read-after-pause, resume,
repeated resume, method and preflight handling, header/body key selection,
malformed input, and both key rotations followed by old/new credential reads.

Three callers admit the prefixes of the first 4, 12 or all 37 operations.
Stopping at any of these prefixes is permitted. Other operation orders are
outside these particular caller languages.

The independent reference uses the following rules:

* A key resolves one project and one privilege class. Reads accept either class;
  pause/resume accept the write class. The resolved native object is handed to
  the view unchanged. A UUID for another project's check is forbidden; a foreign
  project-specific unique key is absent from the authorized project's lookup.
* Reads preserve the store. Read-only responses omit the six write-capable fields
  and include the stable unique key. The reference also specifies the other
  fields for the explicitly initialized check, error bodies, metadata and cookies.
* Pausing a non-paused check records one processed transition and persists
  `paused`. Pausing it again leaves both the check and log unchanged. Resuming
  a paused check records a processed transition to `new`; a repeated resume
  returns conflict and preserves the store.
* A key rotation uses the returned native key as the new credential, updates only
  the designated project/key slot, and preserves every other stored column.
  A separate HMAC calculation checks the persisted replacement. Subsequent calls
  check both rejection of the retired key and acceptance of its replacement.

The rich observation includes the exact status; complete JSON object or exact
non-JSON error body; all response headers and cookies; the resolved Project
class, identifier and read-only/version context; the manager result and its
same-object handoff; all selected Project, Check, Profile and Channel columns;
and the ordered Flip records. JSON member order is immaterial. CORS method-list
order is normalized, while its values and all other headers remain observable.
The retained body is independently checked against the parsed JSON and its
byte-length header.

Flip creation and processing timestamps are kept in the raw observations.
The checked vector retains timestamp presence and the processed-at-creation
relationship rather than predicting a clock reading. It retains Flip ids,
order, owner, old/new status and reason. There is no claim that the physical
database, its clock values or an unbounded Flip log have finitely many states.

## Production diagnosis and actual replay

Native collection completes all 37 operations before diagnosis. Every record
must use the declared fixed routing, and its raw `before` store must equal the
preceding raw `after` store. The full initial state is checked independently.

`production.py` encodes each structured observation injectively into Boolean
state bits. The core allowing event denotes capture of that observation; it
does not grant access. The HTTP status remains an observable field. The
collector also provides a status-only comparison to measure what that interface
loses.

The existing executable checker permits at most 16 caller states. Consecutive
blocks of at most 15 events fit this envelope. Each block has at most 30 distinct
reference/native outcomes plus its reserved initial encoding, with the precise
codebook stored in the artifact. The implementation checks the codebook bound
before invoking the production algorithms. Encoding-block boundaries do not
reset the application: both reference and actual outcomes come from the same
full native prefix, and the raw boundary store is retained and verified.

Both `protocol_binding_profile` and
`support_indexed_protocol_profile` run with the singleton core family `[{}]`
for each concrete routing configuration. Their results are checked against an
independent comparison of the structured vectors. A whole caller passes exactly
when all its blocks pass under that configuration. Its first failing prefix is
the earliest block failure plus the block's absolute offset. The result is
shortest in that caller's prefix-closed word, not among arbitrary HTTP histories.

Every negative configuration is then executed again from a fresh native
database through its required distinguishing prefix. The retained replay
records reproduce both the rich and status-only first differences. Passing
proper prefixes are included in that actual execution.

## Results

For the intended routing, the six combinations of credential format and API
version give the same first-difference positions:

| Source arm | Rich observation | HTTP status alone |
| --- | ---: | ---: |
| Original | All 37 operations agree | All 37 operations agree |
| Read-only context omitted | 1 | All 37 operations agree |
| Project object replaced | 1 | 2 |
| Pause persistence omitted | 15 | 18 |
| Read-only GET rejected | 1 | 1 |

The project replacement's first event is an object-handoff discrepancy: the
fresh ORM query returns another instance for Alice's same project. The second
event exposes the wrong-project lookup when Bob's read is rejected. The missing
pause save first disagrees in committed Check state; its status-only difference
appears when the subsequent resume returns conflict. The read-only propagation
control preserves all declared HTTP statuses while exposing extra response
fields. These are different failures at the application boundary.

`results/native-healthchecks/summary.json` reports the exact request, SQL,
production-comparison and replay totals. The broader routing configurations
and all three callers are retained in `profiles.json.gz`; they are not counted
as additional independent applications.

## Reproduction and retained evidence

From the artifact root, create a Python environment, install the pinned native
closure, and choose a fresh output directory:

```bash
python -m venv runtime-healthchecks
runtime-healthchecks/bin/pip install -r source_study/native_healthchecks/requirements.lock
mkdir -p results/native-healthchecks-work/tmp
TMPDIR="$PWD/results/native-healthchecks-work/tmp" \
  runtime-healthchecks/bin/python -m source_study.native_healthchecks.run all \
  --output results/native-healthchecks-reproduction
```

The one command checks installed dependency records, verifies the retained
upstream source bytes, creates exact source controls, performs native collection,
runs production and independent diagnosis, executes fresh native replays, runs
the unchanged upstream tests, and recomputes the retained summary. The individual
commands are `acquire`, `diagnose`, `replay` and `upstream`.

The retained results can be rechecked without installing the native application
dependencies. This read-only command uses the standard library and distributed
AuthRefine checker, opens every retained SQLite file in read-only mode, and
requires exact agreement with the retained summary:

```bash
python -m source_study.native_healthchecks.run verify --output results/native-healthchecks
```

The observer, source and CLI regression checks run with:

```bash
runtime-healthchecks/bin/python -m unittest discover -s tests -p test_native_healthchecks.py -v
runtime-healthchecks/bin/python -OO -m unittest discover -s tests -p test_native_healthchecks.py -v
```

The optimized invocation propagates its optimization level into native
subprocesses. The two actual-execution tests require the pinned native closure;
the other ten tests check retained evidence and observer behavior.

The output retains the full executed source controls and diffs; source history
and license; native dependency records; physical SQLite files; full HTTP/ORM/SQL
observations; the declared protocol and concrete configurations; exact encoding
codebooks and production traces; actual replay receipts; and the upstream test
receipt. `summarize.verify` reconstructs scientific results from these records.

## Observation admission and scalar types

Structured equality preserves Boolean, integer and floating-point values.
The parsed response must agree with the actual wire body in both values and
types before either rich or HTTP-status projection. Thus a length-preserving
wire edit cannot disappear behind a status-only check. Full profiles require
all 37 declared records. The independent replay entry explicitly admits a
measured prefix; such a prefix can establish a failure but cannot certify
agreement on an unobserved continuation. The focused tests include wire-only
type changes, consistent typed response changes and truncated-input controls.
