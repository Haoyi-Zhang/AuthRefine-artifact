# Native Healthchecks request histories

This study executes every word of length at most three over three original
Healthchecks API operations: a read-only GET of Alice's check, a read/write
PAUSE of that check, and a read/write RESUME. It records the full request tree
from both new and paused initial states. Request order is a variable of the
experiment, rather than a single prescribed lifecycle.

The original 37-operation study remains in ../native_healthchecks/ and
../../results/native-healthchecks/. That study includes the second project,
malformed requests, key rotation and four concrete credential routings.
This study adds complete bounded history coverage for the three-operation
interface under the intended routing. Both execute the same application.

## Language, initial states and source

The alphabet is get, pause, resume. GET carries Alice's read-only API key;
the two POST operations carry her write key. The initial state contains two
real users, profiles, projects, checks and channels, including their
many-to-many association rows. Alice's check is either new or paused. Bob's
check is new and remains present as an unchanged owned record. Neither check
has a last-start, last-ping or alert timestamp.

Each initial state admits all words of length zero through three: 40 history
nodes, including the initial node, and 39 HTTP edges. Five source arms,
two initial key formats, three API versions and two initial statuses give
60 trees and 2,340 primary native requests.

The complete original source modules, license and dependency lock are reused
from ../native_healthchecks/. Executed controls are separately copied and
their exact source diffs retained. No application import, ORM method, API view,
clock function or response is replaced. The controls have the same meanings
as in the existing study:

* omit read-only arguments at the three current serialization call sites;
* substitute a fresh ORM query for the resolved Project handoff;
* omit the pause handler's Check save;
* use the write-authorizing decorator for single-check GET.

The public issue and historical patches retained by the existing study
motivate the read-only controls. These are edits of the retained current
complete modules, not re-executions of historical deployments.

## Every physical history has its own checkpoint

Django constructs the schema and initial objects using the original models.
After each request completes and its database connection closes, the collector
saves the complete SQLite byte image as a gzip-compressed checkpoint. This
preserves every persistent table, association, sequence counter and schema
object, including all Flip rows, identifiers and exact clock values.

Before a child request, the collector restores its actual parent's exact
SQLite bytes and copies its HTTP client's cookie jar. It checks both the byte
copy and full persistent-table snapshot before invoking the original endpoint.
Each child is a real Django Client request through URL dispatch, key lookup,
authorization, the original view, serialization and ORM writes. The module and
framework environment remain loaded; the selected handlers use the request,
database and current clock rather than a mutable cross-request application
object. Request model instances come from the original ORM lookup.

No two history nodes are merged. Equal Check status does not identify stores
with different Flip histories. Rejected and no-operation requests also retain
distinct nodes. The wall clock is not restored or replaced.

Raw records include HTTP method/path/body/key, full response text and parsed
JSON, every response header and cookie, the manager's actual returned Project
and its object-identity handoff, client cookies, every persistent table before
and after the request, and SQL executed during the request. Checkpoint readback
and initial schema/fixture construction are not counted as request SQL.

## Independent expectations follow the expected path

specification.py imports no application or framework module. Its reference
starts from the declared new/paused state and follows each request word:

* GET returns the complete read-only representation and preserves the store;
* PAUSE changes a non-paused check to paused and appends one processed Flip;
  PAUSE of a paused check preserves the rows and log;
* RESUME changes paused to new and appends one processed Flip; RESUME of a
  non-paused check returns 409 and preserves the store.

The expected child state comes from the expected parent transition. It is
never reset to the actual parent state. For the omitted-save arm, a response
can describe paused while the committed Check remains new. Its children execute
from that actual faulty store while the independent contract continues from
paused.

The rich comparison includes the HTTP and handoff information and all
persistent database columns, schema and association rows. Only newly created
Flip clock literals are projected to timestamp presence and the
processed-at-creation relation. Exact timestamps remain in the raw records
and checkpoint images. JSON member order and CORS method-list order are
immaterial; their values and other metadata remain observable. A separate
comparison retains only HTTP status.

JSON comparisons preserve scalar types: false and 0, true and 1, and an
integer and a floating-point value are distinct. The same rule checks raw
wire text against parsed JSON, parent/child snapshots and cookies, exact
SQLite readback, retained profiles and the final summary.

Both comparison entry points require the complete, duplicate-free set of
39 nonempty request words before returning a full-tree result. A replay instead
requires exactly every prefix of its declared word. Missing edges, duplicate
words, wrong parent stores, inconsistent cookies or wire/body metadata are
rejected before semantic classification.

## Production encoding and bounds

Each first operation defines a prefix-closed branch: the empty word and all
words beginning with that operation. Each branch has 13 edges and 14 target
nodes. Its caller uses five internal prefix states plus one terminal state.
A core request consists of the parent history label, native operation and
observation-capture action. Erasing the label gives a length-preserving bijection
between admitted core words and native words in that branch. An independent
traversal checks this bijection and verifies that the three branch languages
have union exactly the 40-word bounded native language.

A branch has at most 26 distinct reference/actual outcomes. Reserving zero for
the initial observation needs at most five bits. Its 13 rules have two guards
and five constant updates each, so the worst-case AST has 104 nodes. Five
principals, three resources, one action, 14 target states and six caller states
fit the existing production envelopes. encoding.bound_probe() exercises both
production algorithms with all 26 outcomes distinct before native acquisition.

An event's core allow bit means observation capture. The HTTP authorization
result remains inside the value; capture does not grant access. Both production
caller-profile algorithms use the singleton family [{}] for each fixed tree.
This is a configuration history check, not a shared-target correspondence
family. They agree with the independent structured observations and recover
the same shortest decoded branch word. All three branches must pass for the
whole language to pass. Global shortestness takes the minimum branch failure
with the same lexical tie-break. See ENCODING.md for the argument.

## Negative-prefix replay

The independent comparison retains every first-bad prefix: its last observation
differs while all proper prefixes agree. Every negative longer word extends
one of these prefixes.

For each source/key-format/API/initial-status stratum, the union of rich and
status first-bad prefixes is deduplicated by native word. Every such word is
executed again from newly created native objects and a fresh database.
Replays preserve their complete checkpoints and requests. Check UUIDs must
differ from all primary and other replay fixtures. Verification checks the
exact first word for every relevant mode, not only its length.

## Retained results

The unmodified source agrees under both observations at all 39 nonempty
histories in each initial-state/key-format/API stratum. The omitted pause
save has different shortest words under the two initial states:

| Initial status | Rich observation | HTTP status |
| --- | --- | --- |
| new | pause | pause, resume |
| paused | resume, pause | resume, pause, resume |

From paused, the initial pause is a no-operation. A preceding resume is needed
to make the next pause require a saved update. This is why the rich failure
moves to two requests and the HTTP-only failure to three.

The following counts are first-bad prefixes in one format/API stratum.
All six strata have the same result. A prefix is counted separately under
each observation whose first failure it witnesses.

| Executed source | Initial status | Rich prefixes | Status prefixes |
| --- | --- | ---: | ---: |
| Original | new or paused | 0 | 0 |
| Omitted read-only context | new or paused | 7 | 0 |
| Replaced Project handoff | new or paused | 3 | 0 |
| Omitted pause save | new | 7 | 5 |
| Omitted pause save | paused | 5 | 1 |
| Rejected read-only GET | new or paused | 7 | 7 |

All 60 trees retain 2,400 full physical checkpoints and 2,340 HTTP edges.
The requests execute 8,580 recorded SQL statements. There are 120 complete
tree/observation results, 360 root-branch components and 720 production
method comparisons. Every one of the 396 first-bad-prefix results is
reproduced by native execution: after deduplicating identical words between
the observation modes, 312 fresh runs execute 732 HTTP requests and retain
another 1,044 complete physical checkpoints.

The replaced-Project control changes the actual object handoff at every
request but preserves HTTP statuses in this single-project alphabet.
The earlier 37-operation study also queries Bob's check and exposes the
project-attribution error there. These are different caller languages.

## Reproduce and verify

From artifact/, install the existing pinned native closure and choose a new
output directory:

    python -m venv runtime-healthchecks
    runtime-healthchecks/bin/pip install -r source_study/native_healthchecks/requirements.lock
    runtime-healthchecks/bin/python -B -m source_study.native_healthchecks_tree.run all --output results/native-healthchecks-tree-reproduction

Set TMPDIR to a writable directory if the host requires it. The acquire,
diagnose and replay stages are also available separately.

Retained results can be checked with Python's standard library and the
distributed core, without Django:

    python -B -m source_study.native_healthchecks_tree.run verify --output results/native-healthchecks-tree

Verification only reads the result directory. SQLite images are deserialized
into an in-memory read-only connection and compared against every retained
full snapshot. Verification checks source diffs, the complete native grid,
all history nodes and checkpoints, exact production profiles, and every fresh
negative-prefix replay; it then requires equality with summary.json.
Source manifests must contain exactly the 34 unique retained paths. All
27 runtime module locations must agree with the recorded source argument.
Collection flags, case indexes, native process exit codes and emitted request
counts are validated for both primary acquisition and replay. Historical
absolute command paths describe the recorded run; the verifier checks their
internal relationships while reading the current result-directory location.

Focused tests:

    runtime-healthchecks/bin/python -B -W error -m unittest discover -s tests -p test_native_healthchecks_tree.py -v
    runtime-healthchecks/bin/python -B -W error -OO -m unittest discover -s tests -p test_native_healthchecks_tree.py -v

The final execution receipts and complete logs are retained separately in
../../results/native-healthchecks-tree-validation/. The 21-test suite passes
under both ordinary and optimized Python with the pinned native dependencies;
two tests perform fresh native tree executions. The standard-library verification
passes without Django installed and leaves all 4,068 scientific input files'
bytes and modification times unchanged. Validation logs are outside the
scientific result directory so that later validation does not alter its input
population.

The summary gives measured counts and shortest rich/status words by source arm
and initial state. Complete branch inputs and outputs, all first-bad prefixes
and individual native records remain alongside the summary.
