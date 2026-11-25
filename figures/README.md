# AuthRefine figures

The paper contains seven statistical figures and two conceptual figures
(the motivating examples and the overview of the two-stage example); the
technical supplement contains six statistical figures. The thirteen
statistical figures are generated here by one Matplotlib script,
`paper_figures.py`, from the retained records of this repository. The
conceptual figures are drawings rather than data plots and are not generated
by the artifact.

The script is distributed unchanged as the manuscript's
`figure-source/make_figures.py`; `figstyle.py` holds the shared style. Text is
set in Times New Roman with STIX mathematics, fonts are embedded as TrueType
(no Type 3), and each PDF is sized for the 5.95 in ACM manuscript text block.
Before drawing, every renderer checks the denominators and headline values that
the manuscript quotes, so a changed record stops the build instead of
producing a silently different plot. The script also writes the six median
rows of the cost table (`family-cost-rows.tex`) from the raw seven-run records.

## Figure sources and scientific inputs

All input paths are relative to `artifact/`.

| Document | Figure | Scientific input |
| --- | --- | --- |
| Main (RQ1) | `validation-profiles.pdf` | `results/support-indexed/summary.json`, `results/support-overlap/summary.json`, `results/protocol-grouping/summary.json` |
| Main (RQ2) | `source-controls.pdf` | `results/source-observer/source-controls.json` |
| Main (RQ3) | `session-certification.pdf` | `results/session-initial-state/validation.json.gz` |
| Main (RQ4) | `width.pdf` | `results/width.csv` |
| Main (RQ4) | `family-diagnosis-cost.pdf` | `results/symbolic-comparison/{summary,trials}.json` |
| Main (RQ4) | `session-correspondence.pdf` | `results/session-correspondence/diagnosis.json`, `results/symbolic-comparison/` |
| Main (RQ4) | `symbolic-comparison.pdf` | all 158 tasks in `results/symbolic-comparison/` |
| Supplement | `source-interface-coverage.pdf` | `source_study/data/source-transfer.json.gz` |
| Supplement | `evaluation-design.pdf` | `prospective_study/{primary,secondary}.json.gz` |
| Supplement | `source-screening.pdf` | `adaptation_study/survey.json.gz` |
| Supplement | `adaptation-handling.pdf` | `adaptation_study/casebook.json` |
| Supplement | `frontend-batch-cost.pdf` | `source_study/data/frontend-cost.json.gz` |
| Supplement | `credential-algorithm-cost.pdf` | `source_study/data/credential-cost.json.gz` |
| Main (table) | `family-cost-rows.tex` | `results/symbolic-comparison/summary.json` |

The timing loader admits the six-method campaign only if it has 158 tasks,
seven repetitions, 42 processes and 5,320 timed records, every worker record
compared complete outputs, all methods returned the same complete profile on
each task, and every summarized median equals the median of the raw samples.

## Regenerate the figures

Install the pinned environment (`pip install -r requirements-figures.txt`).
From `artifact/`:

```sh
python3 -B figures/build_paper_figures.py --output-directory /path/to/fresh-figures
```

The destination must be new. It receives the thirteen PDFs,
`family-cost-rows.tex` and `figure-receipt.json`, which records the SHA-256 of
every PDF, the Matplotlib version and the font provenance.

Byte-identical PDFs require the four Times New Roman 7.12 TrueType files whose
SHA-256 digests are declared in `figstyle.py` (`times.ttf`, `timesbd.ttf`,
`timesi.ttf`, `timesbi.ttf`). These files are proprietary and not distributed.
Put them in a directory and set `AUTHREFINE_FONT_DIR` to it. The receipt's
font status is then `declared`, and `evaluate.py --profile core` requires each
regenerated PDF to equal `../paper/figures/` (or, without the manuscript, the
digests in `manuscript-figures.sha256.json`). Without the declared files the
figures are drawn in a substitute serif face, every data check still runs,
the generated table rows are still compared byte for byte, and the receipt
records PDF byte comparison as unavailable.

## Reading the plots

Timing plots use seven-run medians; intervals and whiskers span the observed
minimum and maximum, not confidence intervals. In the complete-family cost
figure, the whiskers of a product/indexed ratio span
`[min(product)/max(indexed), max(product)/min(indexed)]`. The cumulative
comparison normalizes scan, finite-domain and CUDD times by the support-indexed
time on the same task; ratios below one favor the compared method, and each
panel keeps its own denominator (38, 40 or 80 tasks). Caller languages and
initial stores are tasks on the same source interfaces, not independent
applications. The RQ1 figure shows outcome shares per diagnosis and the
distribution of shortest distinguishing lengths per classified binding row on a
logarithmic axis.
