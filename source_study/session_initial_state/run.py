#!/usr/bin/env python3
"""Acquire fresh native initial-store evidence, or verify it without dependencies."""
import argparse
import asyncio
import gzip
from itertools import permutations
from pathlib import Path
import platform
import sys
import time

ART = Path(__file__).resolve().parents[2]
for directory in (ART, ART / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
sys.dont_write_bytecode = True

from source_study.session_initial_state.io import encoded, read, same, write


def acquire(output):
    # Reject any existing directory before loading dependencies or source.
    if output.exists():
        raise ValueError("output directory already exists; choose a fresh destination")
    from source_study.historical_h19.source import check_native
    from source_study.session_correspondence import fixtures
    from source_study.session_initial_state import collector, strategies
    from source_study.session_initial_state import provenance
    from source_study.session_initial_state.contract import CONTRACT, METHODS, SOURCE
    gate = check_native()
    provenance.validate_dependency_record(gate)
    code_before = provenance.code_identities()
    cases = strategies.cases()
    inputs = {"contract": CONTRACT,
              "fixture_rows": {str(n): fixtures.serialized_rows(fixtures.rows(n)) for n in range(2, 7)},
              "candidate_families": {str(n): [list(beta) for beta in permutations(range(1, n + 1))] for n in range(2, 7)},
              "cases": cases}
    output.mkdir(parents=True, exist_ok=False)
    write(output / "inputs.json.gz", inputs)
    write(output / "native-dependencies.json.gz", gate)
    inputs_before = provenance.identity(output, "inputs.json.gz")
    started_utc = provenance.utc_now()
    started = time.perf_counter()
    counts = {"native_cases": 0, "production_requests": 0, "fixture_reconstructions": 0}
    with (output / "native-traces.jsonl.gz").open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
            def record(value):
                stream.write(encoded(value) + b"\n")
                stream.flush()
                counts["native_cases"] += 1
                for event in value["events"]:
                    counts["production_requests" if event["action"] in ("lookup", "remove") else "fixture_reconstructions"] += 1
            manifests = asyncio.run(collector.acquire(cases, record))
    finished_utc = provenance.utc_now()
    elapsed = time.perf_counter() - started
    code_after = provenance.code_identities()
    if not same(code_before, code_after) or not same(inputs_before, provenance.identity(output, "inputs.json.gz")):
        raise ValueError("code or declared inputs changed during native acquisition")
    if not same(check_native(), gate):
        raise ValueError("native dependency contents or versions changed during acquisition")
    write(output / "source-execution.json", manifests)
    write(output / "acquisition.json", {
        "status": "ACQUIRED", "source": SOURCE, "methods": METHODS,
        "source_admission": "source_study/stateful_sequence/source.py",
        "dependencies": "source_study/historical_h19/requirements.lock",
        "dependency_check_passed": bool(gate), "baseline_source_modified": False,
        **counts, "elapsed_seconds": elapsed, "started_utc": started_utc, "finished_utc": finished_utc,
        "provenance": {"code_before": code_before, "code_after": code_after,
                       "inputs_before": inputs_before,
                       "evidence_files": [provenance.identity(output, path) for path in provenance.EVIDENCE_PATHS],
                       "native_dependencies_rechecked": True},
        "python": platform.python_version(), "platform": platform.platform()})
    print(encoded({"status": "ACQUIRED", **counts}).decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("acquire", help="execute actual source requests into a new directory")
    collect.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify", help="read-only validation of all native histories and binding survivors")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--report", type=Path, help="optional new validation report; existing files are rejected")
    args = parser.parse_args()
    if args.command == "acquire":
        if args.output.exists():
            parser.error("output directory already exists; choose a fresh destination")
        acquire(args.output)
    else:
        if args.report is not None and args.report.exists():
            parser.error("report file already exists; choose a fresh file")
        from source_study.session_initial_state.validation import verify
        result = verify(args.input)
        retained = args.input / "validation.json.gz"
        if retained.exists() and not same(read(retained), result):
            raise ValueError("retained validation report differs from native evidence")
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            write(args.report, result)
        print(encoded({key: value for key, value in result.items() if key != "cases"}).decode())


if __name__ == "__main__":
    main()
