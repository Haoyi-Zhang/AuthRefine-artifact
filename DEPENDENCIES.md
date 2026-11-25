# Dependencies

## Core algorithms and full tests

The finite contract algorithms and independent table audits use the Python
standard library. The full experiment campaign uses Linux CPython and the
POSIX `resource` module for CPU and peak-RSS measurements. Use a Linux
environment or WSL for that workflow.

The complete test suite also exercises native policy evaluation, request
objects, YAML, SQL expressions and serialized records. Install the pinned
packages in `requirements-test.txt` into an isolated environment:

```sh
python3 -m venv /tmp/authrefine-checks
/tmp/authrefine-checks/bin/python -m pip install -r requirements-test.txt
PYTHONDONTWRITEBYTECODE=1 /tmp/authrefine-checks/bin/python -B verify_release.py --output /tmp/authrefine-check
```

The selected Casbin distribution provides the `casbin` import. Do not install
`casbin` and `pycasbin` together in that environment. Local modules such as
`checker`, `compiler` and `cases` are repository code, not package-install
instructions.

On Linux, peak RSS is reported in KiB and CPU/wall time in seconds. These
environmental measurements are separated from scientific result comparisons.
The measured correspondence experiment records CPython 3.12.14 and its host
description in its own acquisition/timing records.

## Native Piccolo studies

Use separate environments for these complete dependency locks:

- `source_study/historical_h19/requirements.lock`: Piccolo 1.16.0, used by
  the native session lifecycle, correspondence and minimum-dependency patch
  experiments;
- `source_study/historical_h19/requirements-1.34.lock`: Piccolo 1.34.0,
  used by the second published-patch configuration.

The two versions are experimental inputs: their metadata behavior differs.
Study loaders verify the selected source and dependencies before executing.
The scripts do not install packages. Native session/correspondence tests skip
explicitly when their environment is absent; run those subsets under the
first lock to exercise them.

## Native Conet policy-store study

The native Conet module and its actual source repair use
`source_study/native_policy_store/requirements.lock`. Install that lock in a
separate environment so Casbin and the complete module's JWT imports match
the retained experiment. Its native tests check actual methods, files and
new-instance reloads. The study README gives the acquisition and verification
commands; retained-record checks use only the standard library.

## Native Healthchecks HTTP study

Install `source_study/native_healthchecks/requirements.lock` in a separate
environment. The complete selected application modules use Django, its native
ORM and SQLite, together with the source closure's pinned imports. The driver
verifies installed dependency records and original source bytes before native
acquisition. It does not install dependencies or contact a running service.
`source_study/native_healthchecks/README.md` describes the local API configuration,
actual key replacement, upstream test modules and physical database records.
The retained-data verifier uses the Python standard library and reads SQLite
without changing its contents.

## Compiled symbolic comparison

`requirements-symbolic.txt` installs `dd` 0.6.0 and its declared dependencies
for the recorded CPython 3.12 x86-64 Linux environment. The experiment uses
the package's compiled `dd.cudd` backend with dynamic variable reordering
enabled. `pip install --only-binary=dd -r requirements-symbolic.txt` selects
the available native wheel while permitting the small Python dependencies
to build their wheels. No CUDD binary is required by the core algorithms or
by read-only verification of the retained comparison records.

The portable finite-domain and CUDD implementations share the Boolean
construction and complete-output contract. Their conditional-operation
counters denote different units; compare task time rather than treating
those operation counts as equivalent. The requirements pin the actual
dependency used for receiver reproduction.

## Other source replay environments

The credential replay described in `source_study/README.md` uses non-root
Linux, Python 3.12+, bubblewrap and prlimit. Its preparation command obtains the
frozen Django/asgiref/sqlparse wheel profile, and its isolated replay has separate
environment requirements. Native Piccolo/SQLite execution does not substitute
for that workflow.

## Paper, figures and proofs

The paper needs a complete TeX Live installation with pdfLaTeX, BibTeX, the ACM
class dependencies, Libertine/Biolinum, Inconsolata, newtxmath, stmaryrd and
algorithmicx; its build instructions (`BUILDING.txt`) are distributed with the
manuscript sources, not with this repository. Figure generation uses
Matplotlib 3.11.2 with the pins in `requirements-figures.txt`; byte-identical
PDFs additionally need the Times New Roman files declared in
`figures/figstyle.py`, which are not distributed; see `figures/README.md`.

The thirteen Lean sources use Lean 4.8.0. Its compiler is an external
dependency; the proof runner downloads nothing and rejects failed checks or
`sorry` warnings. The lockfiles identify the tested dependencies for receiver reproduction.
