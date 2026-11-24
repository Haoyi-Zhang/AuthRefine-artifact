# Independent review of the native request-history study

The bounded study records all words of length at most three over GET, PAUSE
and RESUME from new and paused initial Check states. Five source arms, two key
formats and three API versions give 60 distinct trees. This review checks the
scientific records independently of the collector and its production checker.

## Physical histories and exact outputs

`audit_native_healthchecks_tree.py` uses the Python standard library. It reads
every compressed SQLite image into an in-memory connection, enables query-only
mode and runs SQLite's integrity check. It then compares the complete schema,
all persistent tables, association rows, row identities and sequence counters
with the recorded snapshot. It verifies the parent store and cookie state at
every edge. The 2,400 primary and 1,044 replay checkpoints all pass.

The audit derives the complete 40-word language independently. It verifies
the exact 60-case Cartesian grid, 2,340 primary HTTP edges and their 8,580
recorded SQL statements. Separate lifecycle equations reconstruct each
observed Check state, ordered Flip history and HTTP status, including the
omitted-save control. The reference path starts from its declared initial
state and follows the request word; it does not inherit a faulty actual state.

For every retained production component, the audit traverses its caller and
target together. History-labelled events erase bijectively to the branch's
14 native words. The three branches have union exactly the 40-word language.
All 360 branch inputs respect the existing bounds. Their codebooks preserve
the complete structured actual observation, and their constant reference
updates have the expected equality or inequality at every event. Decoding the
720 production results checks 720 individual replay rows, fixed bindings,
state continuity, agreeing proper prefixes and the canonical shortest native
word. This review decodes retained outputs; it does not invoke a production
checker or execute additional application requests.

The independent first-bad-prefix sets contain 396 observation-specific
results. Deduplication by stratum and native word leaves 312 fresh replay
words and 732 additional HTTP requests. Those replays contain 2,664 recorded
SQL statements and 1,044 physical checkpoints. All 744 Check UUIDs from the
primary and replay fixtures are distinct. Replay words reproduce their exact
first conflicting prefix under each designated observation.

## Source and execution provenance

The audit checks all 34 original source identities, each arm's exact unique
source-file set, the 170 copied source records and every actual control patch.
It checks nine successful native-process receipts: five primary collectors
and four replay collectors. Their 372 collection entries, command arguments,
standard-output counts and 27-module import maps agree with the selected
source closure. Recorded dependency versions and file-identity records agree
with the 17-entry lock. This comparison checks retained dependency evidence;
it does not reinstall or newly inspect the dependency environment.

Recorded absolute acquisition paths are checked for internal consistency.
Their old directories need not exist when the artifact is moved: copied
source bytes and relative result paths are read from the current artifact.

## Findings and their repairs

Two concrete failures were found in the initial review implementation and
reproduced using separate review copies or in-memory records.

1. **Provenance fields were incompletely admitted.** A duplicate manifest
   entry could preserve the reported source-file count while omitting a
   required file. Altered module maps, collection flags, edge counts and
   unsuccessful process receipts were also not all checked. The new admission
   gate requires the complete unique source set, exact module mapping and
   collection index, successful process receipts and consistent counts.
2. **Python numeric equality hid JSON type changes.** An integer zero and
   Boolean false compared equal. A wire-only change from `n_pings: 0` to
   `n_pings: false`, with legal whitespace preserving Content-Length, could
   pass the initial wire/parsed-body check. The recorded parsed value then
   concealed the changed wire value from diagnosis. Type-sensitive comparison
   now covers response parsing, independent observations, persisted rows,
   parent continuity, production inputs and retained summary equality.

The exact original combined provenance challenge is rejected after the
repair. Twenty independently applied post-repair controls exercise each
provenance gap, missing or duplicate history words, JSON and SQLite type
distinctions, extra response fields and headers, changed native-object
handoff, untouched credential slots, association rows, sequence counters and
client cookies. Malformed evidence is rejected; well-formed changed outcomes
receive the expected three-request diagnosis. The control results are in
`results/native-healthchecks-tree-review/post-fix-controls.json`.

The strict independent audit passed on the original scientific records before
and after these admission repairs. All 4,068 native-study files retained their
byte contents and modification times during each audit. No original
observations, checkpoints, profiles, source-control records or native
execution counts were changed to obtain the passing review.

## Reproduction

From `artifact/`, both commands are read-only:

```sh
python -B proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review
python -B -OO -W error proofs/audit_native_healthchecks_tree.py --verify-retained results/native-healthchecks-tree-review
```

The default mode prints the independently recomputed summary. `--results`
selects a relocated native-study directory. `--output` saves a new audit result
and rejects an existing destination, an input ancestor or a path inside the
protected scientific/source directories. Four independent CLI controls verify
these protections. `summary.json` records the complete counts;
`review-findings.json`, `post-fix-controls.json` and `cli-protection.json`
record the repairs and acceptance evidence.
