# Native Healthchecks observation-chain review

The review closes three concrete observation gaps and checks the delivered
native records through the production capture encodings and fresh replays.
The repeatable reader is audit_native_healthchecks.py. It does not execute the
application, acquire new observations, or modify the retained scientific data.

## Run the review

From the artifact directory:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_native_healthchecks.py --results results/native-healthchecks

The default prints a compact result and creates no output files. The reader uses
the Python standard library and the delivered pure Python contract, observation
and core diagnostic modules; it does not require a running Django service or
network access. SQLite connections use read-only mode.

To retain another review result, provide a new directory:

    PYTHONDONTWRITEBYTECODE=1 python proofs/audit_native_healthchecks.py --results results/native-healthchecks --output results/native-healthchecks-review-reproduction

The output path must not exist and must be outside the scientific result
directory. The reader rejects an invalid destination before starting its review.
It records five JSON files: summary, source review, native review, profile review
and observation controls. An existing review directory is never overwritten.

The recorded native subprocess commands contain the absolute paths used during
acquisition. The reviewer checks imported-module ancestry against those recorded
source roots, then opens the corresponding relative files in the delivered
source-controls directory. It never tries to open an earlier workspace or
requires a staging directory to exist.

The source admission check requires the complete, duplicate-free 34-file
closure and the exact 27-entry module-name-to-source-path mapping in every
main and fresh-replay receipt. It checks successful process receipts with
type-sensitive integer exit codes. An empty module map, a missing module,
or a module redirected to another existing source file is rejected.

## What was independently checked

The reader reconstructs the entire case grid: five source arms, two initial key
formats, three API interfaces and four separately executed credential-routing
configurations. Each of the 120 cases contains the same declared 37-event word,
including 35 actual HTTP requests and two calls to the native key producer.
Raw before/after snapshots must form one continuous physical prefix. HTTP bodies
must agree with their parsed records and byte-length metadata. Each rotation
must change exactly its physically routed Project credential slot, with the
stored digest recomputed independently from the returned key.

All five selected SQLite tables are opened anew in read-only mode for every
case. Every column of their final Project, Check, Flip, Profile and Channel rows
must equal the retained physical snapshot. The audit also checks the original
source bytes, each exact declared control edit, the recorded diffs, and every
application module's ancestry in the source tree used by its subprocess.

The profile review reuses the reviewed declarative contract and observation
functions. It independently decodes the retained capture rules, target states,
caller transitions, codebooks and replay rows. The decoded reference values
must equal the contract vectors; the decoded target values must equal the
vectors obtained from the actual native records. This is a review of the saved
observation/encoding chain, not a claim that two different implementations of
an entire application specification have been verified.

Every capture component has a singleton empty binding, an injective codebook,
complete constant assignments for its declared event, and the exact linear
caller language. The physical boundary stored at each encoding block must be
the preceding native event's after-store. The reader derives each local and
whole-word first failure directly from vector equality and checks every saved
proper-prefix comparison. The application is not restarted at encoding boundaries.

For each negative case, a fresh native prefix must reproduce all of its reported
negative caller/observation witnesses. The fresh fixture identities must differ
from those in the main acquisition and from all other fresh replays. The
upstream-test receipt is checked separately. The final physical database of
each of the 114 fresh prefixes is also reopened and compared with its last
recorded store; these checks are separate from the 120 main-case databases.

## Type and completeness admission

Both the independent profile and production comparison admit the complete
physical record before applying an observation projection. Equality preserves
JSON scalar types, including the difference between a number and a Boolean.
For example, replacing a wire-body integer zero by `false`, while removing
whitespace to preserve Content-Length and leaving the parsed record unchanged,
must fail admission even for a status-only profile. A consistent change to both
wire and parsed values instead reaches the rich observation comparison and is
reported at the changed event. Raw parent/child stores, decoded vectors,
configuration fields and summary receipts use the same type-sensitive rule.

The normal entry point requires all 37 operations. A replay may supply its
explicit shorter length and certify the first failure in that prefix; it cannot
report whole-caller agreement while later operations are missing. The final
admission review records the concrete challenged copies, positive controls,
ordinary and optimized tests, and unchanged scientific input files in
`results/validation/legacy-http-admission-review.json`. The genuine native tests
are recorded separately in `results/validation/native-http-tests.json`.

## Concrete gaps closed during review

The initial review identified the following failures of observation coverage.
The delivered reviewer repeats the controls on the corrected original identity
case. These are deliberate changes to copies of retained records, not claims
that the unmodified application produced the changed values.

| Initial observation gap | Retained regression control | Corrected first event |
| --- | --- | ---: |
| Error bodies and unlisted response fields disappeared during projection | Change a JSON error body; change the timeout in a successful response | 11; 1 |
| The manager's native Project object was recorded but its handoff was not checked | Return the other Project in the captured manager evidence and break object identity | 1 |
| Rotation checked its replacement key but omitted the other persisted credential slots | Corrupt the other project's readonly key and carry it through every subsequent physical snapshot | 30 |

Three additional controls retain this coverage for preflight response metadata,
an unexpected error-response cookie, and a non-JSON error body. They fail at
events 21, 11 and 10. The changed JSON/text controls update Content-Length as
well, so detection depends on the response contract rather than inconsistent
record bookkeeping.

The reader changes one compared output at each of the 37 event positions and
checks that the whole-protocol first-failure length is exactly that position.
This covers both block boundaries and both key-producer events. A separate
positive control reorders CORS method tokens, the explicitly declared header
normalization, while preserving equivalence. No other response difference is
removed by that control.

## Retained results

| Reviewed item | Count |
| --- | ---: |
| Native cases | 120 |
| Native events | 4,440 |
| Native HTTP requests | 4,200 |
| Native key rotations | 240 |
| Final SQLite snapshots compared column by column | 120 |
| Source-file checks across five source arms | 170 |
| Imported native application modules per source arm | 27 |
| Configuration/caller/observation profiles | 720 |
| Production capture component comparisons | 2,400 |
| Decoded saved negative replay rows | 3,552 |
| Fresh native replay cases | 114 |
| Fresh native replay HTTP requests | 480 |
| Negative witnesses reproduced by those prefixes | 600 |
| Original upstream API tests passed | 30 |
| Targeted observation controls | 7 |
| Individually checked first-failure positions | 37 |

All six unmodified identity cases agree: both key formats at all three API
interfaces. The other routing configurations are different actual inputs with
separately acquired targets; they are not members of one shared-target family.
The main fixtures contain 240 distinct Check identities. The fresh prefixes
contain another 228, disjoint from the main fixtures.

For identity routing, the first rich-vector and status-only discrepancies are:

| Source arm | Rich vector | HTTP status only |
| --- | ---: | ---: |
| Unmodified source | Match | Match |
| Omitted readonly serializer context | 1 | Match |
| Replaced authorization Project object | 1 | 2 |
| Omitted pause persistence | 15 | 18 |
| Rejected readonly GET | 1 | 1 |

Each result repeats in all six key-format/API strata. In the replaced-Project
control, the first request receives a new ORM instance with Alice's same primary
key. It therefore breaks the manager-to-request object-identity handoff while
still returning the expected HTTP response. The second request is the first
wrong-project attribution and HTTP 403. The first event should be described as
an object-handoff discrepancy, not as an already demonstrated cross-project
access.

## Claim supported by the review

The corrected observation chain checks complete JSON objects, exact non-JSON
bodies, response headers and cookies, native authorization-object handoff, and
the selected persisted rows. Raw Flip clock literals remain available; their
compared representation records presence and processing relations rather than
assuming a predictable clock reading. The first-failure claims concern prefixes
of the declared finite caller words for each separately executed configuration.
The review found no remaining blocking discrepancy for this stated claim.
