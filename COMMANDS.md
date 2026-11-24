# Commands

Run from the repository root (called `artifact/` in the study documents). Every output directory must be fresh.

```sh
python3 -B evaluate.py --profile core --output /fresh/core
python3 -B evaluate.py --profile portable --output /fresh/portable
python3 -B run_campaign.py --output /fresh/campaign
python3 -B verify_research_depth.py --output /fresh/research-depth.json
(cd references && python3 -B verify.py)
python3 -B figures/build_paper_figures.py --output-directory /fresh/figures
```

Exact optional environments use `framework`, `query`, `proofs` or `full`. Exit status 2 means the declared environment is unavailable; exit status 1 means an available profile executed and failed. `status.json`, `receipts/` and `FAILURE_SEMANTICS.md` define the interpretation.

The manuscript sources are not part of this repository. When they are placed next to it as `../paper/`, the figure check compares against `../paper/figures/` (otherwise against `figures/manuscript-figures.sha256.json`), the reference audit additionally checks the bibliography and citation locations, and `python3 -B build.py --targets main submission supplement` run there rebuilds the manuscript views.
