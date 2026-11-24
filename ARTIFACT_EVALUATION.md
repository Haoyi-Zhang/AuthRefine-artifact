# Artifact evaluation status

## Reviewer entry point

```sh
python3 -B review.py --scope core --output /fresh/review
```

This wrapper records one durable log pair per top-level step and writes `review.json` for success, failure, or timeout. `--scope extended` adds the portable matrix, finite campaign, research-depth audit, and bibliography audit. A timeout terminates the whole child process group, so a failed review cannot leave descendants running or wait indefinitely for an inherited output pipe.

`status.json` is the authoritative machine-readable summary. The repository separates a self-contained scientific core, a broader portable regression matrix, and exact external environments. No profile rewrites expected values, removes adverse samples, or converts an unavailable dependency into a pass.

## Core profile

```sh
python3 -B evaluate.py --profile core --output /fresh/core
```

Each mode runs 183 tests in isolated module interpreters: 169 pass and 14 explicitly named optional-native or CUDD checks skip; no test fails or errors. The profile also checks the 1,260 credential contexts, 1,232 paired source observations, 2,896 control inputs, initial-store evidence, the identity/swap example and exact regeneration of 16 vector figures.

## Portable profile

```sh
python3 -B evaluate.py --profile portable --output /fresh/portable
```

This profile expands the gate to all 72 self-contained top-level test modules. In normal, optimized and strict-warning modes it runs 824 tests; on Python 3.13, 800 pass and 24 explicitly skip (on 3.12, one further test of the 3.13-only `ast.dump(show_empty=...)` API skips: 799 pass, 25 skip). Module isolation prevents imports, monkey patches, caches or database state in one test file from affecting another.

## Scientific campaign and evidence audits

```sh
python3 -B run_campaign.py --output /fresh/campaign
python3 -B verify_research_depth.py --output /fresh/research-depth.json
(cd references && python3 -B verify.py)
```

The campaign freshly recomputes 10,000 primary finite cases and 1,340,425 counted obligations. The depth audit rechecks the 23,040-pair finite domain, 43,776 binding profiles, 18,225 caller-family instances and retained complete-output timing records. Reference verification covers 68 bibliography entries and 83 manuscript citation occurrences. The project-disjoint source-transfer replay remains source-level evidence rather than a whole-application or vulnerability study.

## Retained native-record audits

The package includes independent standard-library verifiers for the retained
Healthchecks executions and bounded request-history trees.  They re-read every
recorded database image, request edge, profile and replay row without importing
the application adapters.  The current receipts cover 120 configuration cases
and 60 complete history trees.  These checks validate the retained records; they
do **not** claim a fresh third-party application execution.  See
`receipts/native-records.json`.

## Exact external environments

`framework`, `query`, `proofs` and `full` profiles stop at preflight when their exact dependencies or tools are missing. In the recorded environment they are `UNAVAILABLE`; retained native, CUDD, timing and Lean records are not described as fresh executions. GitHub workflows install the declared dependencies or Lean toolchain in separate jobs.

## Interpretation

Passing core and portable receipts support the supplied-family finite diagnosis, selected source boundaries, fault controls and packaged implementation. They do not establish prevalence, automatic discovery of every candidate family, whole-application correctness, a universal performance ranking or end-to-end formal verification of the Python implementation.
