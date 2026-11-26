# AuthRefine

Research artifact for the paper *AuthRefine: Complete Diagnosis for Supplied
Families of Authorization Correspondences* by Haoyi Zhang, Huaijin Ran,
Jiongchi Yu, Yuqiang Sun and Yang Liu (submitted to ACM TOSEM).

AuthRefine diagnoses finite, stateful authorization contracts when a reviewer
has several fixed interpretations of how contract names correspond to
implementation entities.  Given a supplied legal family, a target observation
and an admitted request language, it returns:

- every interpretation consistent with all admitted traces; and
- one shortest, fully replayable counterexample for every excluded
  interpretation.

The repository contains a typed controlled language, compiler, independent
checker, total-table and caller-profile algorithms, source observers, native
experiments, equal-output comparisons, Lean proof sources, raw data and the
retained results behind every table and figure of the paper.  The guarantee is
relative to the supplied family and observation boundary; AuthRefine does not
infer a complete family or certify an entire application by itself.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/` | contract language, compilation, diagnosis and checking |
| `tests/` | isolated unit, evidence and fault-control tests (profiles in `test_environments.json`, `TESTING.md`) |
| `source_study/` | source snapshots, observation boundaries and native studies |
| `adaptation_study/`, `prospective_study/`, `reference_completion/`, `empirical_study/` | source-transfer and replication studies |
| `benchmarks/` | finite audits and equal-output comparisons |
| `proofs/` | Lean 4 proof sources, proof notes and independent theorem audits |
| `results/` | retained scientific inputs, raw measurements and summaries (`data_inventory.json` classifies each directory) |
| `figures/` | data-driven statistical-figure generation (Matplotlib); `manuscript-figures.sha256.json` holds the digests of the 13 paper figures and the generated cost-table rows |
| `references/`, `reference_*.csv`, `claim_evidence_ledger.csv` | bibliography metadata, reading records, citation audits, claim-to-evidence ledger |
| `external_inputs/` | third-party (Casbin) inputs with their licenses |
| `receipts/`, `status.json` | compact receipts of the authors' recorded validation runs |
| `docs/` | repository layout, evidence scope, third-party materials, native interfaces |
| `review.py`, `evaluate.py`, `run_campaign.py`, `verify_research_depth.py`, `Makefile` | entry points |
| `requirements-*.txt` | exact pins for each optional environment |

Study documents inside sub-folders say "run from `artifact/`": that is the root
of this repository.  Further reviewer documentation:
[ARTIFACT_EVALUATION.md](ARTIFACT_EVALUATION.md), [TESTING.md](TESTING.md),
[REPRODUCIBILITY.md](REPRODUCIBILITY.md), [DEPENDENCIES.md](DEPENDENCIES.md),
[DATA_AND_EVIDENCE.md](DATA_AND_EVIDENCE.md), [COMMANDS.md](COMMANDS.md),
[FAILURE_SEMANTICS.md](FAILURE_SEMANTICS.md).

## Requirements

- **OS:** Linux x86-64 (tested: Ubuntu 24.04 under WSL2).  Some code uses POSIX
  process groups, `resource` and POSIX paths, so native Windows is not
  supported; use WSL2 or Docker.  macOS is untested.
- **Python:** CPython 3.13 (recommended; the installation below obtains it with
  [uv](https://docs.astral.sh/uv/), no root needed) or 3.12.  The core
  algorithms, the test suites of the `core`/`portable` profiles, the campaign
  and all audits use only the standard library.  On 3.12 everything also
  passes, but one portable test that exercises the 3.13-only
  `ast.dump(show_empty=...)` API is skipped with the reason
  "show_empty was added in Python 3.13".  `make` and `git` are used by the
  entry points and one test.
- **Figure regeneration** (part of `make review`): Matplotlib 3.11.2 and its
  pinned dependencies (`requirements-figures.txt`).  The figures are set in
  Times New Roman; byte-identical PDFs need the four Times New Roman 7.12
  TrueType files whose SHA-256 digests are declared in `figures/figstyle.py`
  (a directory named by `AUTHREFINE_FONT_DIR`).  These files are proprietary
  and not distributed; without them every data check still runs, the generated
  table rows are still compared, and the receipt records PDF byte comparison as
  unavailable.
- **Optional exact environments:** see the table in
  [What needs extra tools](#what-needs-extra-tools).
- **Hardware / disk / time:** one CPU core and < 1 GB RAM suffice; the
  repository is about 200 MB and the evidence of a full review run about 60 MB.
  `make review` takes about 1.5 minutes, `make review-extended` about 10 minutes.

## Installation (Linux)

```sh
# uv (single static binary) provides CPython 3.13 without root
curl -LsSf https://astral.sh/uv/install.sh | sh     # installs ~/.local/bin/uv
~/.local/bin/uv python install 3.13
~/.local/bin/uv venv -p 3.13 --seed ~/venvs/authrefine   # outside the repository
. ~/venvs/authrefine/bin/activate                  # python3 is now CPython 3.13
pip install -r requirements-figures.txt

# Optional, for byte-identical figure PDFs: the declared Times New Roman files
export AUTHREFINE_FONT_DIR=/path/to/times-new-roman   # times.ttf, timesbd.ttf, timesi.ttf, timesbi.ttf
```

No package build step is required; run every command from the repository root.
All targets write to fresh directories below `$EVIDENCE` (default
`/tmp/authrefine-evidence`); existing outputs are never overwritten, so run
`make clean` (or pass another `EVIDENCE=...`) before repeating a target.

A container alternative: `docker build -t authrefine .` and
`docker run --rm -v "$AUTHREFINE_FONT_DIR":/fonts:ro -e AUTHREFINE_FONT_DIR=/fonts authrefine`
(runs `make review`'s core scope; not tested by us).

## Quick check (about 1.5 minutes)

```sh
make review
```

Expected final line:
`{"receipt": "/tmp/authrefine-evidence/review/review.json", "scope": "core", "status": "PASS"}`.
The receipt `/tmp/authrefine-evidence/review/core/evaluation.json` records, for
each of the normal, `-O` and `-OO -W error` modes, 183 tests (169 pass, 14 named
skips for optional native/CUDD checks), the motivating identity/swap example,
the source-observer evidence and the regeneration of all 13 statistical
figures and the generated cost-table rows (`"figures": {"ok": true,
"pdf_byte_comparison": "performed", ...}` when the declared fonts are present).

Minimal diagnostic example by hand:

```sh
python3 -B source_study/stateful_sequence/export_profile_inputs.py --output /tmp/authrefine-inputs
python3 -B src/profile.py /tmp/authrefine-inputs/policy.json /tmp/authrefine-inputs/machine.json \
  /tmp/authrefine-profile.json --family /tmp/authrefine-inputs/family.json
```

The two-session example retains identity and excludes swap with the shortest
sequence `remove(row-a); lookup(credential-a)`.

## Full reproduction

| Paper evidence | Command | Output | Expected | Time |
| --- | --- | --- | --- | --- |
| Contribution-critical tests, motivating example, source-observer evidence, all 13 statistical figures | `make core` | `$EVIDENCE/core/evaluation.json` | `PASS`; per mode 183 tests / 169 pass / 14 skips; 13/13 figures and the cost-table rows byte-identical (figures: with the declared fonts) | 1.5 min |
| Complete self-contained regression matrix | `make portable` | `$EVIDENCE/portable/evaluation.json` | `PASS`; 72 modules, per mode 824 tests / 800 pass / 24 named skips on Python 3.13 (799 / 25 on 3.12, where one AST test needs 3.13) | 7.5 min |
| 10,000-case finite-model campaign, 23,040-pair exhaustive domain, theory/extension/adversarial records, 49 readable examples | `make campaign` | `$EVIDENCE/campaign/` | `"status": "PASS"`, 10,000 primary cases, 1,340,425 counted obligations, `scientific_match: true`; `examples/` byte-identical to `results/examples/` | 20 s |
| Finite rechecks behind the cost and caller-family tables; reaggregation of retained timing/native records | `make depth` | `$EVIDENCE/research-depth.json` | `"status": "PASS"` | 20 s |
| Claim-evidence ledger reconciliation (+ bibliography and citation locations if `../paper/` is present) | `make references` | stdout JSON | `"status": "PASS"` (`"manuscript_checks": "SKIPPED"` without `../paper/`) | 10 s |
| The 13 statistical figures of the paper and supplement | `make figures` | `$EVIDENCE/figures/` | PDFs and `family-cost-rows.tex` whose SHA-256 equal `figures/manuscript-figures.sha256.json` | 30 s |
| All of the above except `figures` (core already includes it) | `make review-extended` | `$EVIDENCE/review-extended/review.json` | `PASS` | 10 min |

Which result backs which paper claim is recorded in
[`claim_evidence_ledger.csv`](claim_evidence_ledger.csv) (claim, manuscript
location, proof, source/test, raw evidence, reproduction command); per-study
commands are in [REPRODUCIBILITY.md](REPRODUCIBILITY.md) and the study READMEs
listed under [Experiments and data](#experiments-and-data).

## What needs extra tools

These profiles report `UNAVAILABLE` (exit 2) when their exact environment is
absent, never a pass.  Install each into its **own** virtual environment.

| Target | Needs | Expected | Verified by us |
| --- | --- | --- | --- |
| `make proofs` | Lean **4.8.0** on `PATH` (e.g. `elan toolchain install leanprover/lean4:v4.8.0`, or the release archive from GitHub); no Mathlib | `PASS`; 13 Lean files, no `sorry` | yes, PASS in 5 s |
| `make query` | `pip install -r requirements-query.txt` | `PASS` | yes, PASS in 2 s |
| `make framework` | `pip install -r requirements-test.txt` | `PASS` (363 tests per mode, no skips) | yes, PASS in 1.2 min |
| CUDD audit `python -B proofs/audit_symbolic_family.py` | `pip install -r requirements-symbolic.txt` (CPython 3.12, x86-64) | `"status": "passed"` | yes |
| `make full` (`verify_release.py`) | the `requirements-test.txt` environment plus Lean 4.8.0 (`lean`, `lake`) on `PATH` | `PASS` | yes, PASS |
| `make paper` | `../paper/` and a TeX Live with pdfLaTeX/BibTeX and the packages listed in `../paper/BUILDING.txt` (commands below) | `{"completed": true, ...}` | yes, with TeX Live 2026 |
| Fresh native acquisitions (Healthchecks, Pretix, Piccolo, Conet, Casbin variants, ...) | the locked per-study environments in `source_study/*/README.md` and `requirements-native*.txt` (mutually exclusive Casbin/pycasbin installs), `bwrap`, `prlimit` | new raw records | only the credential-admission re-collection below |

Installing these tools without root (each Python environment separate; run
from the repository root, after the [installation](#installation-linux) above):

```sh
# Lean 4.8.0 (make proofs, make full)
curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
  | sh -s -- -y --no-modify-path --default-toolchain leanprover/lean4:v4.8.0
export PATH="$HOME/.elan/bin:$PATH"
elan toolchain install leanprover/lean4:v4.8.0   # download now, not on first use
lean --version                                    # Lean (version 4.8.0, ...)
make proofs

# query and framework / full environments
~/.local/bin/uv venv -p 3.13 --seed ~/venvs/authrefine-query
~/venvs/authrefine-query/bin/pip install -r requirements-query.txt
make query PYTHON=~/venvs/authrefine-query/bin/python
~/.local/bin/uv venv -p 3.13 --seed ~/venvs/authrefine-test
~/venvs/authrefine-test/bin/pip install -r requirements-test.txt
make framework PYTHON=~/venvs/authrefine-test/bin/python
make full PYTHON=~/venvs/authrefine-test/bin/python      # needs Lean on PATH

# compiled CUDD audit (CPython 3.12)
~/.local/bin/uv python install 3.12
~/.local/bin/uv venv -p 3.12 --seed ~/venvs/authrefine-cudd
~/venvs/authrefine-cudd/bin/pip install --only-binary=dd -r requirements-symbolic.txt
~/venvs/authrefine-cudd/bin/python -B proofs/audit_symbolic_family.py

# TeX Live in user space for make paper (about 800 MB, needs ../paper/)
curl -fsSL https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz | tar -xz -C /tmp
cat > /tmp/texlive.profile <<EOF
selected_scheme scheme-basic
TEXDIR $HOME/texlive
TEXMFLOCAL $HOME/texlive/texmf-local
TEXMFSYSVAR $HOME/texlive/texmf-var
TEXMFSYSCONFIG $HOME/texlive/texmf-config
TEXMFVAR $HOME/texlive/texmf-var
TEXMFCONFIG $HOME/texlive/texmf-config
TEXMFHOME $HOME/texlive/texmf-home
instopt_adjustpath 0
tlpdbopt_install_docfiles 0
tlpdbopt_install_srcfiles 0
EOF
perl /tmp/install-tl-2*/install-tl --profile=/tmp/texlive.profile
export PATH="$HOME/texlive/bin/x86_64-linux:$PATH"
tlmgr install collection-latexrecommended collection-latexextra \
  collection-fontsrecommended collection-mathscience collection-bibtexextra \
  libertine inconsolata newtx txfonts kastrup stmaryrd algorithms algorithmicx
make paper
```

`make paper` rebuilds `main.pdf` (45 pages, 68 references, seven statistical
figures and three conceptual-figure placeholders) and `supplement.pdf` (40 pages,
six statistical figures) in `../paper/` (it overwrites them; use a copy if you
want to keep the distributed PDFs).  Other TeX Live releases may change line or
page breaks.

The retained `results/credential-admission-review/` records (checked by
`make full`) were re-collected with the shipped
`benchmarks/audit_credential_admission.py` in the
`source_study/native_healthchecks/requirements.lock` environment (CPython
3.12, Django 6.1.2); all observations and admission outcomes equal the
earlier collection, only the recorded script hash and runtime fields changed.
To repeat it:

```sh
~/.local/bin/uv venv -p 3.12 --seed ~/venvs/authrefine-healthchecks
~/venvs/authrefine-healthchecks/bin/pip install -r source_study/native_healthchecks/requirements.lock
~/venvs/authrefine-healthchecks/bin/python -B -W error benchmarks/audit_credential_admission.py --mode all --output /tmp/authrefine-credential-admission
python3 -B -W error benchmarks/audit_credential_admission.py --mode check --results /tmp/authrefine-credential-admission
```

Stand-ins for what is not re-executed: retained native application records,
compiled-CUDD timings and historical timing measurements are in `results/`
(classified in `data_inventory.json` and [DATA_AND_EVIDENCE.md](DATA_AND_EVIDENCE.md));
the `core`, `portable` and `depth` checks re-verify those records with the
standard library without re-running the applications.  Compact receipts of
the authors' runs are in `receipts/` and `status.json`.

## Manuscript (optional)

The manuscript sources are not part of this repository.  If they are placed
next to it as `../paper/`, `make core`/`make figures` compare against
`../paper/figures/*.pdf` directly, `make references` also checks the
bibliography and every citation location, `tests/test_reference_snapshots.py`
checks manuscript line anchors, and `make paper` rebuilds the PDFs.

## Detailed usage

### Complete-family command line

```sh
python3 -B source_study/stateful_sequence/export_profile_inputs.py --output /tmp/authrefine-inputs
python3 -B src/profile.py /tmp/authrefine-inputs/policy.json /tmp/authrefine-inputs/machine.json /tmp/authrefine-indexed.json --family /tmp/authrefine-inputs/family.json
python3 -B src/profile.py /tmp/authrefine-inputs/policy.json /tmp/authrefine-inputs/machine.json /tmp/authrefine-scan.json --family /tmp/authrefine-inputs/family.json --engine scan
python3 -B src/profile.py /tmp/authrefine-inputs/policy.json /tmp/authrefine-inputs/machine.json /tmp/authrefine-caller.json --family /tmp/authrefine-inputs/family.json --engine protocol-indexed --protocol /tmp/authrefine-inputs/protocol.json
```

The exporter reads the included native/interpreted session tables. It does not
run Piccolo. Supply `--run /path/to/fresh/native/output` to export a newly
acquired table. The two-member family consists of the identity and swapped
credential correspondences. Identity matches; swap has a shortest two-request
witness. Substituting `control-machine.json` checks the introduced omitted
deletion: both interpretations then fail after one request.

| Engine | Target interface | Shared work |
|---|---|---|
| `indexed` | Total table | Target graph and active local-support groups |
| `scan` | Total table | Target graph |
| `protocol-indexed` | Partial table with a supplied caller | Admitted target/caller graph and active local-support groups |
| `protocol` | Partial table with a supplied caller | Admitted target/caller graph |
| `symbolic` | Total table | Legal-family relation and finite-domain mismatch predicates |
| `symbolic-cudd` | Total table | Legal-family relation and compiled CUDD mismatch predicates |
| `protocol-symbolic` | Partial table with a supplied caller | Admitted target/caller graph and finite-domain predicates |
| `protocol-symbolic-cudd` | Partial table with a supplied caller | Admitted target/caller graph and CUDD predicates |

All engines preserve an explicitly supplied correlated family. Omitting
`--family` selects the Cartesian product of the declared alias candidates.
These are different inputs: the two-session example has two supplied bijections
but four Cartesian assignments. Each replay retains one complete binding.

The CUDD engines require `requirements-symbolic.txt`; the finite-domain
engines use the standard library. Symbolic engines additionally accept
`--node-limit` and `--symbolic-operations`. Their operation counters have
backend-specific units. A CUDD node limit checks manager sizes after each
conditional operation, rather than peak allocation inside that native call.

A completed profile exits 0, including a result where some or every
interpretation fails. Invalid inputs exit 1. Exhausted work/family envelopes,
missing enabled edges or inactive equal-initial callers exit 2 without a
partial family output. Existing destinations are never overwritten. The
default work envelope is 2,000,000 engine-specific abstract units and the
default family limit is 65,536 consumed entries, including duplicates. JSON
input and output are bounded by 32 MiB; policy sentence input by 4 MiB.

### Python APIs

```python
from family_diagnosis import support_indexed_profile
from protocol_grouped import support_indexed_protocol_profile

profile = support_indexed_profile(policy, machine, family)
admitted = support_indexed_protocol_profile(policy, partial_machine, caller, family)
```

`symbolic_family.symbolic_family_profile(policy, machine, family=family,
protocol=caller, backend="cudd")` returns the same complete semantic fields.
Omit the protocol for a total table, and use `backend="finite-domain"` for
the portable diagram. Explicit supplied families are encoded without adding
illegal Cartesian members.

Run with `src/` on the module path. `extensions.binding_profile` and
`protocol_profile.protocol_binding_profile` are the ungrouped comparators.
They use the same semantic output fields. `checker.verify_reachable` answers
uniform equivalence and returns a globally shortest fixed-binding failure;
the complete profile continues until every supplied member is classified.

The optional region-list interface `checker.verify` validates a supplied
closed region. A structural rejection of an extra unreachable cell is not
itself a reachable behavioral failure. The `src/policy.py` commands additionally
provide parsing, compilation and uniform diagnosis. These mathematical
interfaces evaluate declared requirements; source observations and the
reviewer's requirement determine their application meaning.

### Experiments and data

| Study | Executable entry | Retained data |
|---|---|---|
| Native correlated session families | `source_study/session_correspondence/run.py` | `results/session-correspondence/` |
| Selected-row observations and duplicate-token control | `source_study/session_correspondence/verify_observation.py` | `results/session-observation/` |
| Native policy file, restart and executed repair | `source_study/native_policy_store/run.py` | `results/native-policy-store/` |
| Native HTTP, key replacement and persisted effects | `source_study/native_healthchecks/run.py` | `results/native-healthchecks/` |
| Complete short native HTTP histories | `source_study/native_healthchecks_tree/run.py` | `results/native-healthchecks-tree/` |
| Native lifecycle and expiry boundaries | `source_study/stateful_sequence/run.py` | `results/native-session/` |
| Published producer/consumer patch | `source_study/historical_h19/run.py` | `results/published-patch/` |
| Independent complete function-body observation | `source_study/independent_observer/run.py` | `results/source-observer/` |
| Typed credential admission with native primitives | `benchmarks/audit_credential_admission.py` | `results/credential-admission-review/` |
| Six-method complete-profile cost | `benchmarks/symbolic_comparison.py` | `results/symbolic-comparison/` |
| Independent six-method evidence audit | `benchmarks/audit_symbolic_comparison.py` | `results/symbolic-comparison-review/` |
| Retained earlier four-method cost | `benchmarks/stateful_family.py` | `results/family-cost/` |
| Overlapping supports and correlated families | `proofs/audit_support_overlap.py` | `results/support-overlap/` |
| Grouped caller profiles | `proofs/audit_protocol_grouping.py` | `results/protocol-grouping/` |
| Total-table support profiles | `proofs/audit_support_indexed.py` | `results/support-indexed/` |
| Ungrouped caller families | `proofs/protocol_family_audit.py` | `results/caller-family/` |
| Minimum covers by shortest session tests | `proofs/audit_session_distinguishability.py` | `results/session-distinguishability/` |
| Optimal session request cost with anchors, adaptation and resets | `proofs/audit_session_operation_cost.py` | `results/session-operation-cost/` |
| Initial-store cost and complete surviving languages | `benchmarks/audit_session_initial_state.py` | `results/session-initial-state/finite-audit.json.gz` |
| Native optimal strategies from partial initial stores | `source_study/session_initial_state/run.py` | `results/session-initial-state/` |

The native correspondence study varies live sessions from two through six
and supplies all bijections, then checks partially established correspondences.
It records complete native transitions, independent equation-based profiles,
physical witness replay and repeated equal-output timing. The smallest
configuration overlaps the earlier two-session lifecycle; the study's 2,808
unchanged-source edges are not added to the earlier 130-pair count as new
independent observations. See its README for exact denominators and commands.

The short-test proof establishes the complete session profile for arbitrary
cardinality and the minimum number of independent shortest tests covering
every incorrect correspondence. Its independent finite audit checks every
word of length at most two and every smaller cover for two through six sessions.
The 576,720 binding/word pairs are equation checks, separate from native source
execution. `proofs/session-distinguishability.md` gives the proof and reproduction
command, and the complete matrices accompany the count summaries.

The operation-cost theorem strengthens the cover result to arbitrary finite
words, adaptive request choices and store resets. From the complete initial
store, certifying identity among all permutations fixing k correct supplied
anchors requires 2 max(n-k-1, 0) requests under decision/presence observation,
or max(n-k-1, 0) with selected-row observation. The uninterrupted construction
attains the bounds. Under a one-removal caller the projected optimum instead
needs max(n-k-1, 0) fresh-store words. The audit checks 124 anchor contexts,
2,369 anchored binding cases and 1,290 fixed-transposition certificates across
458,854 closed-domain transitions. Its reconciliation of 30 retained native
edges adds no new native execution. See `proofs/session-operation-cost.md`
for the proof, boundary examples and read-only reproduction command.

The initial-store extension covers every subset of present rows. With m free
coordinates, d initially missing free rows and b=1 exactly when both presence
classes are nonempty, the minimum request counts are 2 max(m-1,0)-b for
decision/presence and max(m-1,0) for selected-row observation. Exactly one
complete restoration is necessary when d is at least two. Resetting to the
same partial store cannot resolve permutations among its missing rows.
The native study executes 248 optimal strategies over every initial store for
two through six sessions, with 1,434 production requests and 198 complete
fixture restorations. Ten separate reset-to-initial controls execute 160
requests and twenty resets. The independent finite audit covers all 5,456
initial-store/anchor contexts and checks complete surviving languages, with
180 separate optimal belief-state searches. See `proofs/session-initial-state.md`
for the general proof and the distinction between requests and fixture work.

The independent observer executes thirteen complete selected function bodies
from Healthchecks, Pretix and Wger and compares 1,232 declared observations
with a separately implemented interpreter/provider path. Eight executable
source changes supply sensitivity controls. The native session study adds
Piccolo with actual ORM and SQLite execution. The patch study uses that same
application under two dependency environments, so it is not another application
sample. Its 180 metadata comparisons and 210 endpoint calls have separate
denominators.

The Conet policy-store experiment imports the complete policy module with
real Casbin and a file adapter. It records actual reaching prefixes, ordered
physical states, mutations, new-instance reloads and an executed save repair.
The sixteen initial-file/source-arm cases are one application interface, with
3,072 measured edges and 7,440 additional prefix operations. Its full-store
and Boolean-only contracts locate the same lost update at different points
in a request sequence. Conet was already present in the development sample;
the native study adds executable evidence for that interface.

The Healthchecks study executes complete selected application modules through
the Django test client, ORM and SQLite. Each of 120 cases executes a declared
37-operation sequence containing 35 HTTP calls and two native key replacements.
The cases cross key formats, API versions, concrete credential routings and
source controls. Each routing has its own acquired target; the three prefix
callers compare a fixed configuration under HTTP-status and richer observations.
The richer contract records response contents, object transfer and persisted
rows. See `source_study/native_healthchecks/README.md` for the actual request
sequence, source-change meanings, observation schema and fresh replay evidence.

The complementary history-tree experiment executes every word of length at
most three over GET, PAUSE and RESUME from new and paused initial states.
Sixty trees contain 2,340 primary native HTTP edges and 2,400 complete physical
SQLite checkpoints. The expected path continues independently of actual
faulty state. Injective outcome coding and three exact caller branches preserve
native word lengths and shortestness. The 120 outer profiles retain 396
first-conflicting prefixes; 312 distinct fresh native word runs, totaling 732
HTTP requests, reproduce them. Full compressed SQLite images preserve all rows,
associations, schema, sequences and raw clocks. The study has a separate
standard-library read-only verifier; its source guide and ENCODING.md give the
request language, reference construction and production bounds.

The complete six-method comparison runs 158 tasks from the controlled,
session and policy-file cohorts. Every applicable method returns all legal
members, identical canonical shortest words and all fixed-binding replay
fields. Raw process records and seven repetitions accompany the derived
medians; earlier timings remain separately identified in their original
directories.

`results/chunks/` contains the 10,000 ordered primary campaign records and
forty metric files. `results/examples/` contains 49 complete readable examples
(regenerated byte-for-byte by `make campaign` into `$EVIDENCE/campaign/examples/`).
The auxiliary theory, extension, adversarial and independent tiny-domain
records are retained as separate JSON datasets. Their domains and roles are
documented in the supplementary paper.

### Source integration

The [source-study guide](SOURCE_STUDY_GUIDE.md) gives current replay commands
and the supplementary source-transfer figure location. The original
source-study README remains part of its checked input evidence.

`source_study/workflow.py` reconstructs the included guard projections,
discovers closures/captures, executes explicit contexts and builds finite
comparison tables. Its `source` mode accepts another source archive and an
explicit JSON contract. The project also includes:

- `adaptation_study/`: development-exposed source constructs and concrete
  adaptation cases;
- `prospective_study/`: a separate selected transfer cohort, with frozen
  transfer distinguished from adaptation after source inspection;
- `reference_completion/`: source-functional contracts for further entries;
- `empirical_study/`: forty-project source-bound replication records.

Each study README specifies admitted entries, primitive providers, licensing
and available replay. The optional Baserow enterprise entry requires its
separately licensed source. The older equality-coded observation dataset retains its documented provenance;
private source material and unavailable observer fixtures are not included.

### Proofs, references and figures

[proofs/README.md](proofs/README.md) maps the thirteen Lean files to their
checked statements and provides the compiler command. The active-group
arguments and independent executable audits supplement those statements; they
are not extraction of a mechanically verified Python implementation.

`reference_inventory.csv` identifies every cited work. `reference_audit.csv`
records the supported claim and actual reading scope. `claim_evidence_ledger.csv`
maps manuscript claims to their arguments, inputs, results and reproduction
commands. The `references/` tools check the bibliography and citation
locations against retained primary metadata and reading records when the
manuscript sources are available.

All statistical figures are generated by one Matplotlib script from the
delivered data, which checks the plotted denominators and headline values
before drawing. The paper's three conceptual figures (overview, motivating examples and
failure strata) are not data plots and are not generated here.
[figures/README.md](figures/README.md) maps each figure to its inputs and gives
the regeneration command.

## Evidence boundary

Fresh, self-contained checks cover the finite-model campaign, motivating
example, independent oracles, mutation controls, selected source-body
observations, exact initial-store audits and vector-figure reconstruction.
Framework integrations, compiled decision diagrams and Lean compilation have
separate dependency/toolchain receipts.  Retained native or timing records are
identified as retained whenever they are not reacquired in the current
environment.

The project does **not** claim:

- prevalence across authorization systems;
- automatic discovery of every plausible correspondence;
- whole-application correctness from sampled source boundaries;
- a universally fastest diagnostic representation; or
- end-to-end formal verification of the Python implementation.

## Citation and license

Cite the manuscript as given in `CITATION.cff`, with the author order Haoyi
Zhang, Huaijin Ran, Jiongchi Yu, Yuqiang Sun and Yang Liu.

- Code: MIT License ([LICENSE](LICENSE)).
- Data, retained results and documentation: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)).
- Bundled upstream source snapshots and inputs keep their own licenses and
  notices ([docs/third-party-materials.md](docs/third-party-materials.md)).
  The study loaders check the source and dependencies used by each native
  experiment before executing its selected methods.
