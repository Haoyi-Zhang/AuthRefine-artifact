# Repository layout

This repository separates executable research code and retained scientific
evidence. The manuscript is distributed separately. Study documents written
before the repository was split say "from `artifact/`"; that is this
repository's root.

- `src/` contains the finite contract language, compilers, diagnostic
  algorithms, and command-line interfaces.
- `tests/` contains the top-level test modules. Every module belongs to
  exactly one environment profile described in `TESTING.md`.
- `benchmarks/` contains experiment and independent-audit drivers.
- `source_study/` contains source observations, attributed snapshots,
  native-study drivers, and licenses.
- `results/` contains the scientific inputs and raw or aggregated
  records needed by the verifiers. Large native trees are retained because the
  audits inspect physical stores and request histories; historical figure and
  delivery-review directories are intentionally excluded.
- `proofs/` contains Lean statements and independent finite audits.
- `figures/` regenerates the statistical figures and the cost-table rows used
  by the manuscript.
- `figures/manuscript-figures.sha256.json` records the SHA-256 digests of the
  13 statistical figures and the table rows, so the byte-identity check works without the
  manuscript. If the manuscript sources are placed next to this repository as
  `../paper/`, the checks use them directly.

Generated evidence must be written outside the source tree. The review-facing
commands reject non-fresh output directories. Python caches, local virtual
environments, build logs, delivery manifests, and review-round material are not
part of the repository.
