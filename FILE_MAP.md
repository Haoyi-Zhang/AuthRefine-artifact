# File map for reviewers

1. Read `README.md`, `ARTIFACT_EVALUATION.md`, `TESTING.md` and `FAILURE_SEMANTICS.md`.
2. Inspect `status.json` and `receipts/` for the compact current validation summary.
3. Run `evaluate.py --profile core` and start with `motivating-example/validation.json`.
4. Run the `portable` profile for the complete self-contained test matrix.
5. Use `DATA_AND_EVIDENCE.md` and `data_inventory.json` to distinguish fresh, frozen, timing and retained evidence.
6. Rebuild the 13 statistical figures of the paper and supplement with `figures/build_paper_figures.py`.
7. Attempt exact optional profiles only in their declared environments.
8. The paper source is distributed separately (optionally placed next to this repository as `../paper/`); the supplement is separate and the main manuscript has no appendix.
