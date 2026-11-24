# Test and environment profiles

Every top-level module in `tests/` belongs to exactly one profile. Modules run in separate Python interpreters so imports, monkey patches, caches, database state and environment variables cannot leak across test files.

## Reviewer entry point

```sh
python3 -B review.py --scope core --output /fresh/review
python3 -B review.py --scope extended --output /fresh/review-extended
```

The core scope wraps the contribution-critical profile. The extended scope additionally runs the portable matrix, finite campaign, research-depth audit, and reference audit. Every step uses file-backed logs and a separate process group; failure and timeout paths still produce `review.json` instead of leaving an ambiguous partial run.

## Core

```sh
python3 -B evaluate.py --profile core --output /fresh/core
```

Contribution-critical algorithms, protocols, sessions, independent oracles, evidence, the motivating example and figure reconstruction. Each of normal, `-O` and `-OO -W error` executes 183 tests (169 pass, 14 explicit skips).

## Portable

```sh
python3 -B evaluate.py --profile portable --output /fresh/portable
```

All 72 self-contained top-level modules. Each interpreter mode executes 824 tests (800 pass, 24 explicit skips on Python 3.13; on 3.12 one test of the 3.13-only `ast.dump(show_empty=...)` API also skips: 799 pass, 25 skips).

## Framework and query

```sh
python3 -m venv /tmp/authrefine-framework
/tmp/authrefine-framework/bin/pip install -r requirements-test.txt
/tmp/authrefine-framework/bin/python -B evaluate.py --profile framework --output /fresh/framework

python3 -m venv /tmp/authrefine-query
/tmp/authrefine-query/bin/pip install -r requirements-query.txt
/tmp/authrefine-query/bin/python -B evaluate.py --profile query --output /fresh/query
```

These profiles require their exact pinned environments. A missing or mismatched package yields `UNAVAILABLE` before tests run.

## Proofs and full integration

```sh
python3 -B evaluate.py --profile proofs --output /fresh/proofs
python3 -B evaluate.py --profile full --output /fresh/full
```

The proof profile requires Lean on `PATH`, rejects `sorry`, and checks the shipped component theorems. The full profile is the strict integration gate. Missing tools remain `UNAVAILABLE`; no absent environment is converted into a skip or pass. `test_environments.json` is the profile registry.
