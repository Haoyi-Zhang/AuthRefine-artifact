# Session observation and family prerequisites

This study completes the selected-row observation comparison using fresh native
executions of the two Piccolo methods already used in the session-correspondence
study. It also checks a prerequisite of that study's supplied bijection family
against a real database input. The original decision/presence profiles and timing
records remain separate and unchanged.

## Reproduce

From `artifact/`, verify the retained evidence with ordinary Python and the
standard library:

```sh
python3 -B -m source_study.session_correspondence.verify_observation
```

To execute the native operations again, use the environment specified by
`source_study/historical_h19/requirements.lock` and a fresh output directory:

```sh
python -B -m source_study.session_correspondence.verify_observation \
  --acquire --results /tmp/authrefine-observation-study
```

The command validates the selected source and installed native dependencies.
It invokes the existing complete upstream methods through Piccolo and SQLite,
saves the raw observations, and then diagnoses the duplicate-token input. It
does not overwrite the existing session-correspondence data or measure new
algorithm timings. The omitted-delete arm remains an introduced source control.

Focused regression checks, from `artifact/`:

```sh
PYTHONPATH=src:. python3 -B -m unittest discover -s tests \
  -p test_session_observation.py -v
```

## What the complete identity witness contains

The stronger observation adds the selected stored row's identity to the returned
authorization decision and observed row-presence state. Every failing profile
now retains `reference_selected_row`, `observed_selected_row`, `identity_equal`,
and `compared_equal`. The last field is the conjunction of decision, state, and
identity agreement. The native records retain the actual selected row, token
argument, returned user, full stores before and after the call, and deleted row
identities.

For example, under the swapped two-row interpretation, a lookup of
`credential-1` returns the same user and leaves the same two rows present. The
actual source selects row 1; the interpreted reference selects row 2. That is a
one-request identity disagreement, while the decision and state comparisons are
both equal. The complete witness records precisely this distinction.

The acquisition covers the ten existing size/arm cases, each with unrestricted,
lookup-only, and one-removal callers. These give 30 caller profiles and 5,232
binding rows: 20 match and 5,212 are excluded. The word set is deduplicated within
each physical case before native execution, giving 35 one-request executions.
These comprise 30 lookups and five removals. Across the complete profiles,
5,202 excluded binding rows disagree on selected identity; the other ten
disagree on persisted state in the omitted-delete control. Every excluded
binding/caller row is independently compared with the appropriate physical
record, including its declared request word and caller phase.

This richer observation is a source-observation comparison implemented by the
independent direct equations and product oracle. It is not claimed to extend the
general diagnostic backend's binary decision/presence interface. Recording the
selected row requires source-level observation; the public method's returned
user ID alone does not reveal it.

## A family proposal is separate from an explicit contract

The native token column has no uniqueness constraint. The duplicate-token input
changes only the second initial row's token to the first row's token. Native
SQLite accepts both rows. Complete acquisition reaches two states and observes
20 cells, with 30 source calls including their reaching prefixes. One removal
of the first token deletes both matching rows.

`propose_bijections` checks distinct row identities, distinct stored token
values, distinct credential arguments, equal cardinality, and token coverage
before returning the supplied all-bijections review hypothesis. On the original
distinct-token inputs it also records the physical mapping that the token
records identify. The remaining permutations are review hypotheses supplied to
the contract; the records do not establish naturally occurring ambiguity or its
frequency. On the duplicate-token input the prerequisite check returns no
automatic family proposal.

An explicitly supplied one-to-one contract remains a valid diagnostic input.
The four total-interface methods and the scan/grouped methods for all three
callers return the same complete result: both supplied bindings are excluded,
each by a one-request witness. The outcome is `none`, not malformed-input
rejection. This distinction prevents a family-proposal check from hiding a
genuine disagreement with an explicit contract.

The duplicate input checks what the stored schema and selected methods permit.
It is not evidence that ordinary session creation commonly produces duplicate
tokens, or that a production deployment has suffered a token collision.

## Retained records

| File | Contents |
| --- | --- |
| `native-witnesses.json.gz` | Fresh physical executions of every distinct richer-observation witness word. |
| `identity-profiles.json.gz` | All 30 complete caller profiles, including full identity-bearing replays. |
| `duplicate-native.json.gz` | Actual schema properties, initial rows, reaching prefixes, complete native graph, and source-to-table cells for the duplicate input. |
| `duplicate-diagnosis.json` | Proposal outcome, explicit contract and family, and the ten complete comparator profiles. |
| `acquisition.json` | Selected source, native dependency environment, control description, and acquisition scope. |
| `summary.json` | Counts and case summaries derived by the read-only verifier. |

The verifier checks all retained native fields and source-to-table cells, and
binds every witness to its request indices. It reconstructs the richer trace
from physical records using separate direct equations. Focused negative controls
change identity fields, relabel a native selection, substitute a request word,
or break state continuity; these changes must be rejected.
