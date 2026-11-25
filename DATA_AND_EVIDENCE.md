# Data and evidence map

The artifact separates executable inputs, frozen scientific records, environment-dependent measurements and compact validation receipts.

- `results/` contains the raw or canonical scientific records used by the paper. `data_inventory.json` classifies every top-level result directory and records its size and whether the current repository freshly rechecks it or retains it.
- `source_study/`, `prospective_study/` and `external_inputs/` contain source snapshots, licenses and observation boundaries.
- `receipts/` contains compact, path-neutral summaries of the current core, portable, campaign, source-transfer, reference and research-depth runs.
- `figures/` contains the deterministic Matplotlib renderer of the statistical figures; they are rebuilt from the packaged data and compared byte-for-byte when the declared Times New Roman files are available.
- Timing and resource fields are measurements. Retained native, compiled-backend and proof records are never labeled as current executions when their exact environment is unavailable.

No evaluator changes a frozen expected scientific field to make a current run pass. Input errors, execution failures, semantic disagreements, timeouts, skips, unavailable environments and unexecuted retained records remain distinct.
