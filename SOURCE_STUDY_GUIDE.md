# Source-study reproduction and figure navigation

Run the commands below from the repository root. The original
`source_study/README.md` is retained among the source study's checked inputs.
This guide gives the current replay entry points and manuscript figure
location without changing those original input bytes.

## Check the retained source evidence

```sh
python -B -W error source_study/verify.py
python -B -W error source_study/replay.py check
python -B -W error benchmarks/audit_credential_admission.py --mode check
python -B -W error -m source_study.verify_source_observer --results results/source-observer
```

The first command verifies the source-study inputs, complete credential
families, case witnesses and finite property counts. The second checks the
complete credential observation domain and serializer transfers. The
credential-admission audit checks the retained 1,260-context native baseline
and the two exact serializer type controls without importing Django.

The independent source-body verifier reexecutes the selected CPython functions
on owned SQLite records, reproduces the production comparison and eight
source controls, and reconciles the complete retained reports. Its
[study guide](source_study/independent_observer/README.md) identifies the
compared fields, fixture domains and graph-prefix checks.

Fresh native acquisitions use the separate dependency environments and fresh
output paths specified in [REPRODUCIBILITY.md](REPRODUCIBILITY.md). The
non-root frozen-wheel credential replay, the in-process credential-admission
audit and the complete native Healthchecks HTTP study have separate execution
boundaries.

## Current source-transfer figure

The source-transfer coverage figure appears in the supplementary paper under
“Source transfer and historical integration records,” with the caption
“Complete direct-dependency links in 48 matched snapshots.” Its figure file
is `source-interface-coverage.pdf` among the manuscript figures (regenerated
by `make figures`).
The original source-study input document's historical figure number is not a
reference to the current manuscript numbering.

The [figure guide](figures/README.md) maps this plot to
`source_study/data/source-transfer.json.gz` and its Python renderer. The plot
reports structural route-linkage counts; it does not use the independent
source-body observations as a semantic-accuracy denominator.
