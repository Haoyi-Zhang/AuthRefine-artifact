# Complete-output comparison review

This directory contains a read-only audit of the retained six-method comparison.
All 158 tasks, 760 applicable task/method pairs, 42 worker processes, 5,320 timed
records, and 10,529 binding profiles pass. The historical acquisition program
and measurement files have been preserved.

| File | Contents |
| --- | --- |
| `summary.json` | Exact admitted denominators, evidence scope, and immutability result |
| `inventory.json` | Byte counts and content identities for 89 campaign files, nine historical source files, four original scientific inputs, and the symbolic dependency pins |
| `controls.json` | Outcomes of 42 malformed-copy rejection controls and three positive controls |

Run from `artifact/`:

```sh
python -OO -B -W error benchmarks/audit_symbolic_comparison.py --verify-review results/symbolic-comparison-review
```

The command uses the standard Python library, performs no writes, and does not
execute a diagnosis backend or collect timings. The controls are altered
in-memory copies used to test admission; they are not additional measurements.
The process and backend identities checked here are retained metadata and
source identities. The scope and command-line regression tests are explained in
`proofs/symbolic-comparison-review.md`.
