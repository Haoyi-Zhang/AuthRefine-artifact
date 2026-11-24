# References and scientific claims

From `artifact/`, run:

```sh
python -B references/verify.py
```

The command is read-only. It checks the current bibliography against retained
primary metadata, follows the actual `main.tex` and `supplement.tex` input
trees, resolves claim anchors and evidence paths, and recomputes selected
scientific counts and timing summaries from the supplied records. It needs
Python's standard library and does not require network access.

After an intentional manuscript edit, update the derived companions with:

```sh
python -B references/verify.py --write
```

## Canonical records

The three CSV files in the parent directory are the current records:

- `reference_inventory.csv`: bibliographic identities and citation counts.
- `reference_audit.csv`: the claim supported by each citation, the inspected
  source and its reading/access scope, and current manuscript locations.
- `claim_evidence_ledger.csv`: theorem, source, experiment and reproduction
  links for the manuscript's claims.

`reading-records.json` preserves the recorded reading scopes, supported
claims, verification bases, access dates and access notes. Refreshing citation
locations does not create a new source-reading event. The verifier rejects a
change to these preserved fields; a substantive new reading belongs in a
separate reading record.

## Primary metadata and source reading

`crossref/` contains retained publisher-deposited DOI responses.
`non-doi-metadata.json` contains the primary records without a DOI, including
software documentation, change records and issue reports. The metadata report
computes each count from the current bibliography and retained records. Undated
documentation keeps `n.d.`; its access date is not a publication date.
`margrave-ieee-metadata.json` supplies the co-publication page range omitted
from the ACM deposit. The metadata comparison documents abbreviated names,
missing fields, online/print dates and the primary sources used for specific
exceptions. `metadata-access-records.json` preserves the original access
outcomes, including the unsuccessful request and its subsequent retry.

Publication identity and claim support are separate checks.
`source-passage-checks.json`, `additional-source-passages.json` and
`current-source-passages.json` record the passages, abstracts or indexed
material actually inspected. `healthchecks-sources.json` records the official
API contract, a historical response-hardening change, and a read-only GET
rejection report with its maintainer response and linked fix. Its source and
claim locators distinguish current-source controlled regressions from historical
patch reading. A restricted or unsuccessful full-text fetch
remains explicit. The metadata verifier does not upgrade abstract-level
reading to a full-text check. The additional TOSEM genre comparison is kept
separate from the works cited in the bibliography.

## Reproducible data checks

`claims.py` reads the complete support-overlap and caller-family profile
streams; native session inputs, profile restrictions and witness records;
raw timing process outputs; and selected retained source-observer records.
It verifies counts, complete-family consistency, replay lengths, canonical
witness buckets, exact anchored-family restrictions, deterministic work and
output sizes, and every reported timing median and observed range in these
campaigns. It imports no production evaluator.

This reconciliation is not a fresh experiment. The ledger identifies the
independent semantic oracles, source acquisition and benchmark commands
needed to rerun the experiments. `claim-checks.json` reports the retained
data reconciled by this command; `reference-integrity.json` and
`citation-locations.json` describe current manuscript coverage. Source
files outside the included main and supplement trees do not contribute
citation counts.

Individual checks can also be run directly:

```sh
python -B references/metadata.py
python -B references/claims.py
python -B references/refresh.py
python -B -m unittest discover -s references -p 'test_*.py'
```
