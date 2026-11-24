#!/usr/bin/env python3
"""Native source acquisition, correspondence diagnosis and equal-output costs.

Run acquisition with the supplied native dependency environment. Analysis and
timing use only the acquired records and the standard-library checker code.
Each timing process compares its complete result with the independently
checked retained profile after the diagnosis clock has stopped.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import traceback

ART = Path(__file__).resolve().parents[2]
for directory in (ART, ART / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
sys.dont_write_bytecode = True

from source_study.session_correspondence import fixtures

TOTAL_METHODS = ("per-binding-product", "per-binding-target", "shared-target", "support-indexed")
CALLERS = ("unrestricted", "lookup-only", "one-removal")
PROTOCOL_METHODS = tuple(f"protocol-{algorithm}/{caller}" for caller in CALLERS
                         for algorithm in ("scan", "grouped"))
METHODS = TOTAL_METHODS + PROTOCOL_METHODS
SEMANTIC_FIELDS = ("binding", "equivalent", "length", "indices", "trace")
ACQUISITION_SCOPE = "Both baseline and control: selected source loading, temporary database setup, native ORM and SQLite execution, resets, reaching prefixes, rich observations and finite-table construction. The common dependency gate and final JSON encoding/write are outside these clocks."
TIMING_SCOPE = "Diagnosis includes schema validation, normalization and copying of the supplied family, graph construction, reference comparisons, index management and complete fixed-binding witness replay. Permutation enumeration and contract/caller construction are common input preparation. Native observation acquisition, worker module imports, subprocess startup and input parsing are outside per-case clocks. Output encoding is timed separately."


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write(path, value):
    data = encoded(value)
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(data, mtime=0))
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def semantic_rows(report):
    return [{key: row[key] for key in SEMANTIC_FIELDS} for row in report["profiles"]]


def run_method(case, method):
    # Loaded only after native observations have been written in acquisition.
    from benchmarks.stateful_family import run_method as run_total
    from protocol_profile import protocol_binding_profile
    from protocol_grouped import support_indexed_protocol_profile
    if method in TOTAL_METHODS:
        return run_total(case, method)
    algorithm, caller = method.split("/")
    function = protocol_binding_profile if algorithm == "protocol-scan" else support_indexed_protocol_profile
    return function(case["policy"], case["machine"], case["callers"][caller], family=case["family"])


def acquire(output, sizes):
    from source_study.session_correspondence.native import acquire as collect
    from source_study.historical_h19.source import check_native
    destination = output / "native-observations.json.gz"
    if destination.exists():
        raise ValueError("native output already exists; use a fresh destination")
    output.mkdir(parents=True, exist_ok=True)
    dependency_check = check_native()
    acquired, runtimes = [], []
    for size in sizes:
        started = time.perf_counter_ns()
        observed = asyncio.run(collect(size))
        acquired.append(observed)
        runtimes.append({"sessions": size, "acquisition_wall_ns": time.perf_counter_ns() - started,
                         "source_operations": sum(observed[arm]["source_operations"]
                                                  for arm in ("baseline", "omit-delete"))})
        print(f"acquired {size} sessions: {len(observed['baseline']['edges'])} baseline cells", flush=True)
    write(destination, acquired)
    write(output / "fixtures.json", [fixtures.document(size) for size in sizes])
    # Source admission and exact dependency checks happen in existing loaders.
    # Keep the public summary focused on the experiment rather than package IDs.
    write(output / "acquisition.json", {
        "status": "PASS", "python": platform.python_version(), "platform": platform.platform(),
        "native_dependency_check_passed": bool(dependency_check), "records": runtimes,
        "total_acquisition_wall_ns": sum(row["acquisition_wall_ns"] for row in runtimes),
        "timing_scope": ACQUISITION_SCOPE,
        "source": "source_study/source/h19/after/piccolo_api/session_auth/tables.py",
        "source_admission": "source_study/stateful_sequence/source.py",
        "dependencies": "source_study/historical_h19/requirements.lock",
        "selected_methods": ["SessionsBase.get_user_id", "SessionsBase.remove_session"],
        "baseline_source_modified": False, "introduced_control": "remove_session completes without deleting rows",
        "observation_before_policy_import": True,
    })


def check_native_cells(size, graph, control):
    """Compare every acquired rich record with direct lifecycle equations."""
    from source_study.session_correspondence.oracle import step, selected_row
    identity = dict(zip(fixtures.aliases(size), fixtures.credentials(size)))
    requests = fixtures.alphabet(size)
    states = graph["states"]
    if len(graph["edges"]) != len(states) * len(requests):
        raise ValueError("native graph is not complete for its reached stores")
    expected_states = {(1 << size) - 1} if control else set(range(1 << size))
    if set(states) != expected_states:
        raise ValueError("native graph has unexpected lifecycle states")
    checked = 0
    for edge in graph["edges"]:
        state = (1 << size) - 1
        records = edge["prefix_observations"] + [edge["observation"]]
        indices = edge["prefix"] + [edge["input_index"]]
        if len(indices) != len(records):
            raise ValueError("native prefix record count differs from its request word")
        for index, observed in zip(indices, records):
            request = requests[index]
            decision, following = step(size, state, request, identity)
            if control and request[2] == "remove":
                following = state
            expected_selected = selected_row(size, state, request, identity)
            actual_selected = None if observed["selected_record"] is None else observed["selected_record"]["id"]
            expected_before = fixtures.serialized_rows([r for r in fixtures.rows(size) if state & (1 << (r["id"] - 1))])
            expected_after = fixtures.serialized_rows([r for r in fixtures.rows(size) if following & (1 << (r["id"] - 1))])
            expected_result = fixtures.USER if request[2] == "lookup" and decision == "allow" else None
            selected_record = next(({key: row[key] for key in ("id", "token", "user_id")}
                                    for row in expected_before if row["id"] == expected_selected), None)
            checks = [observed["request"] == request, observed["before_state"] == state,
                      observed["after_state"] == following, observed["decision"] == decision,
                      observed["token_argument"] == fixtures.token_for(size, request),
                      actual_selected == expected_selected, observed["selected_record"] == selected_record,
                      observed["returned_user_id"] == expected_result,
                      observed["before_rows"] == expected_before, observed["after_rows"] == expected_after,
                      observed["removed_ids"] == [i for i in range(1, size + 1) if state & (1 << (i - 1)) and not following & (1 << (i - 1))],
                      observed["store_changed"] == (state != following)]
            if not all(checks):
                raise ValueError(f"native rich record disagrees with direct lifecycle equations: {size}, {control}, {request}")
            state = following
            checked += 1
        if edge["observation"]["before_state"] != edge["from_state"]:
            raise ValueError("native graph source coordinate differs")
        machine = graph["machine"]
        position = states.index(edge["from_state"])
        expected_edge = [edge["observation"]["decision"], states.index(edge["observation"]["after_state"])]
        if machine["transitions"][position][edge["input_index"]] != expected_edge:
            raise ValueError("finite target table disagrees with its source record")
    return checked


def analyze(output):
    from source_study.session_correspondence import oracle
    analysis_started = time.perf_counter_ns()
    native_path = output / "native-observations.json.gz"
    frozen = native_path.read_bytes()
    acquired = read(native_path)
    input_read_wall = time.perf_counter_ns() - analysis_started
    cases, summaries, all_profiles, replay_requests = [], [], [], []
    family_preparation, case_preparation = [], []
    for source in acquired:
        size = source["sessions"]
        prepared = time.perf_counter_ns()
        family = fixtures.family(size)
        family_preparation.append({"sessions": size, "bindings": len(family),
                                   "permutation_enumeration_wall_ns": time.perf_counter_ns() - prepared})
        for arm in ("baseline", "omit-delete"):
            graph = source[arm]
            rich_checks = check_native_cells(size, graph, arm == "omit-delete")
            prepared = time.perf_counter_ns()
            case = {"id": f"sessions-{size}-{arm}", "sessions": size, "arm": arm,
                    "policy": fixtures.contract(size), "machine": graph["machine"],
                    "family": family, "callers": fixtures.callers(graph["machine"]["alphabet"]),
                    "expected": {}}
            case_preparation.append({"id": case["id"], "contract_and_caller_construction_wall_ns":
                                     time.perf_counter_ns() - prepared})
            counts = {}
            all_words = set()
            independent = [oracle.profile(size, case["machine"], binding) for binding in family]
            for method in TOTAL_METHODS:
                value = run_method(case, method)
                rows = semantic_rows(value)
                if rows != independent:
                    raise ValueError(f"independent complete-profile disagreement: {case['id']}, {method}")
                case["expected"][method] = rows
                counts[method] = work_counts(value)
            selected = {(graph["states"].index(edge["from_state"]), edge["input_index"]):
                        None if edge["observation"]["selected_record"] is None else edge["observation"]["selected_record"]["id"]
                        for edge in graph["edges"]}
            identity_observations, caller_outcomes = {}, {}
            for caller in CALLERS:
                protocol = case["callers"][caller]
                direct = [oracle.profile(size, case["machine"], binding, protocol) for binding in family]
                expected_matching = len(family) if caller == "lookup-only" else (1 if arm == "baseline" else 0)
                expected_length = None if caller == "lookup-only" else (2 if arm == "baseline" else 1)
                if sum(row["equivalent"] for row in direct) != expected_matching:
                    raise ValueError("unexpected candidate-family outcome")
                if {row["length"] for row in direct if not row["equivalent"]} != (set() if expected_length is None else {expected_length}):
                    raise ValueError("unexpected shortest-witness stratum")
                caller_outcomes[caller] = {"matching": expected_matching, "excluded": len(family) - expected_matching,
                                          "shortest_excluded_length": expected_length}
                for algorithm in ("scan", "grouped"):
                    method = f"protocol-{algorithm}/{caller}"
                    value = run_method(case, method)
                    rows = semantic_rows(value)
                    if rows != direct:
                        raise ValueError(f"independent caller-profile disagreement: {case['id']}, {method}")
                    case["expected"][method] = rows
                    counts[method] = work_counts(value)
                richer = [oracle.profile(size, case["machine"], binding, protocol, selected) for binding in family]
                identity_observations[caller] = [{key: row[key] for key in ("binding", "equivalent", "length", "indices")} for row in richer]
                expected_rich_matching = 0 if arm == "omit-delete" and caller != "lookup-only" else 1
                if sum(row["equivalent"] for row in richer) != expected_rich_matching:
                    raise ValueError("selected-row identity result differs")
                if {row["length"] for row in richer if not row["equivalent"]} != {1}:
                    raise ValueError("selected-row identity should expose each exclusion in one request")
                for row in direct:
                    if not row["equivalent"]:
                        all_words.add(tuple(row["indices"]))
            # A review can supply already-established correspondences. Check
            # genuine correlated subfamilies without completing their product.
            anchors = []
            for fixed in range(1, size):
                anchors.append((f"first-{fixed}-rows-known", {
                    f"credential-for-row-{row}": f"credential-{row}"
                    for row in range(1, fixed + 1)}))
            anchors.append(("inconsistent-first-row", {"credential-for-row-1": "credential-2"}))
            anchored_profiles, anchored_summaries = [], []
            for label, anchor in anchors:
                positions = [position for position, binding in enumerate(family)
                             if all(binding[name] == value for name, value in anchor.items())]
                restricted = {**case, "family": [family[position] for position in positions]}
                records = {}
                for method in ("support-indexed", "protocol-grouped/one-removal"):
                    expected = [case["expected"][method][position] for position in positions]
                    actual = semantic_rows(run_method(restricted, method))
                    if actual != expected:
                        raise ValueError(f"anchored family changed a fixed-binding answer: {case['id']}, {label}")
                    records[method] = actual
                anchored_profiles.append({"name": label, "anchor": anchor, "profiles": records})
                matching = sum(row["equivalent"] for row in records["support-indexed"])
                anchored_summaries.append({"name": label, "anchor": anchor, "family_members": len(positions),
                                           "matching": matching, "excluded": len(positions) - matching,
                                           "exact_restriction_check": True})
            coverage = Counter(tuple(row["indices"]) for row in independent if not row["equivalent"])
            all_profiles.append({"id": case["id"], "profiles": case["expected"],
                                 "selected_identity_profiles": identity_observations,
                                 "anchored_family_profiles": anchored_profiles})
            replay_requests.append({"id": case["id"], "sessions": size, "arm": arm,
                                    "words": [list(word) for word in sorted(all_words)]})
            summaries.append({"id": case["id"], "sessions": size, "arm": arm,
                              "family_members": len(family), "cartesian_family_members": size ** size,
                              "native_states": len(graph["states"]), "native_edges": len(graph["edges"]),
                              "native_prefix_operations": graph["prefix_operations"],
                              "native_rich_record_checks": rich_checks,
                              "caller_outcomes": caller_outcomes, "work": counts,
                              "selected_identity_matching": {caller: sum(row["equivalent"] for row in rows)
                                                             for caller, rows in identity_observations.items()},
                              "selected_identity_excluded_length": 1,
                              "distinct_native_words_requested": len(all_words),
                              "witness_coverage": [{"indices": list(word), "requests": [case["machine"]["alphabet"][index] for index in word],
                                                    "excluded_bindings": count}
                                                   for word, count in sorted(coverage.items())],
                              "anchored_families": anchored_summaries})
            cases.append(case)
            print(f"checked {case['id']}: {len(family)} fixed bijections across {len(METHODS)} methods", flush=True)
    write(output / "inputs.json.gz", cases)
    write(output / "profiles.json.gz", all_profiles)
    write(output / "native-replay-inputs.json", replay_requests)
    write(output / "diagnosis.json", {
        "status": "PASS", "cases": summaries, "method_names": list(METHODS),
        "complete_profile_comparisons": sum(len(case["family"]) * len(METHODS) for case in cases),
        "anchored_family_profiles": sum(len(row["anchored_families"]) * 2 for row in summaries),
        "anchored_binding_comparisons": sum(sum(family["family_members"] for family in row["anchored_families"]) * 2
                                            for row in summaries),
        "independent_oracle": "Direct session equations and an explicit reference × target × caller BFS; no production evaluator or support routine.",
        "native_source_applications": 1, "distinct_upstream_methods": 2,
        "family_design": "Supplied bijections, enumerated exhaustively for each session count; cardinality scaling within one real source interface.",
        "baseline_edges": sum(row["native_edges"] for row in summaries if row["arm"] == "baseline"),
        "control_edges": sum(row["native_edges"] for row in summaries if row["arm"] == "omit-delete"),
        "native_acquisition_not_in_diagnosis_timing": True,
    })
    if frozen != native_path.read_bytes():
        raise ValueError("analysis changed the frozen native observations")
    write(output / "analysis-runtime.json", {
        "native_input_read_wall_ns": input_read_wall,
        "family_preparation": family_preparation, "case_preparation": case_preparation,
        "analysis_wall_ns": time.perf_counter_ns() - analysis_started,
        "scope": "Common permutation enumeration and contract/caller construction are measured separately from diagnosis. Total analysis includes independent oracle checks, ten-method comparisons, anchored-family comparisons and result encoding; it is validation-campaign runtime, not the latency of one diagnosis.",
    })


def work_counts(result):
    return {"semantic_steps": result["transition_evaluations"],
            "replay_steps": result["work_breakdown"].get("replay_steps", 0),
            "graph_cells": result.get("graph_cells_inspected", result.get("graph_edges", 0)),
            "support_queries": result.get("support_queries", 0),
            "index_memberships_created": result.get("index_memberships_created", 0),
            "index_memberships_removed": result.get("index_memberships_removed", 0),
            "peak_cached_memberships": result.get("peak_cached_memberships", 0),
            "matching": sum(row["equivalent"] for row in result["profiles"]),
            "bindings": len(result["profiles"])}


def native_replay(output):
    from source_study.session_correspondence.native import replay_words
    from source_study.session_correspondence.oracle import check_native_witness
    cases = {case["id"]: case for case in read(output / "inputs.json.gz")}
    result, comparisons, case_summaries = [], 0, []
    for task in read(output / "native-replay-inputs.json"):
        records = asyncio.run(replay_words(task["sessions"], task["arm"], task["words"]))
        by_word = {tuple(record["indices"]): record["observations"] for record in records}
        coverage = Counter()
        # The unrestricted complete profile contains every excluded binding.
        # Other callers preserve those selected words or exclude no binding.
        for row in cases[task["id"]]["expected"]["shared-target"]:
            if not row["equivalent"]:
                check_native_witness(task["sessions"], row["binding"], row["indices"], by_word[tuple(row["indices"])] )
                comparisons += 1
                coverage[tuple(row["indices"])] += 1
        for record in records:
            record["excluded_bindings_checked"] = coverage[tuple(record["indices"])]
        case_summaries.append({"id": task["id"], "distinct_native_words": len(records),
                               "native_operations": sum(len(row["observations"]) for row in records),
                               "excluded_bindings_checked": sum(coverage.values()),
                               "coverage": [{"indices": list(word), "excluded_bindings": count}
                                            for word, count in sorted(coverage.items())]})
        result.append({"id": task["id"], "sessions": task["sessions"], "arm": task["arm"], "words": records})
    write(output / "native-witness-replay.json.gz", result)
    write(output / "native-replay-summary.json", {
        "status": "PASS", "distinct_native_word_runs": sum(len(row["words"]) for row in result),
        "native_operations": sum(len(word["observations"]) for row in result for word in row["words"]),
        "excluded_binding_replays_checked": comparisons,
        "cases": case_summaries,
        "reuse": "Each different physical request sequence is natively executed once per case; its rich source records are checked separately under every excluded fixed binding selecting that sequence.",
    })


def child(method):
    cases = json.loads(sys.stdin.buffer.read())
    # Module loading is common setup, outside every per-case clock.
    import benchmarks.stateful_family
    import protocol_profile
    import protocol_grouped
    records = []
    for case in cases:
        started, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = run_method(case, method)
        elapsed, cpu_elapsed = time.perf_counter_ns() - started, time.process_time_ns() - cpu
        rows = semantic_rows(result)
        begun = time.perf_counter_ns()
        data = encoded(rows)
        serialization = time.perf_counter_ns() - begun
        if rows != case["expected"][method]:
            raise ValueError("timed result differs from the independently checked complete profile")
        records.append({"id": case["id"], "diagnosis_wall_ns": elapsed, "diagnosis_cpu_ns": cpu_elapsed,
                        "serialization_ns": serialization, "output_bytes": len(data),
                        "complete_output_equal": True, **work_counts(result)})
    print(json.dumps({"method": method, "records": records}))


def benchmark(output, repeats):
    if type(repeats) is not int or not 3 <= repeats <= 15:
        raise ValueError("repeats must be in 3..15")
    cases = read(output / "inputs.json.gz")
    data = encoded(cases)
    trials_dir = output / "timing-trials"
    trials_dir.mkdir(exist_ok=False)
    trials = []
    for repeat in range(repeats):
        order = METHODS[repeat % len(METHODS):] + METHODS[:repeat % len(METHODS)]
        for method in order:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", method]
            started = time.perf_counter_ns()
            process = subprocess.run(command, input=data, capture_output=True, timeout=300,
                                     env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            process_wall = time.perf_counter_ns() - started
            name = f"repeat-{repeat + 1}-{method.replace('/', '-') }"
            (trials_dir / (name + ".json")).write_bytes(process.stdout)
            (trials_dir / (name + ".stderr.txt")).write_bytes(process.stderr)
            if process.returncode != 0:
                raise ValueError(f"benchmark process failed: {name}")
            value = json.loads(process.stdout)
            if value["method"] != method or [r["id"] for r in value["records"]] != [c["id"] for c in cases]:
                raise ValueError("benchmark returned the wrong cohort")
            value.update(repeat=repeat + 1, process_wall_ns=process_wall)
            trials.append(value)
        print(f"timed rotated repeat {repeat + 1}/{repeats}", flush=True)
    summary = []
    clock_fields = ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns")
    for case in cases:
        row = {"id": case["id"], "sessions": case["sessions"], "arm": case["arm"], "methods": {}}
        for method in METHODS:
            values = [next(r for r in trial["records"] if r["id"] == case["id"])
                      for trial in trials if trial["method"] == method]
            deterministic = {key: value for key, value in values[0].items() if key not in clock_fields}
            if any({k: v for k, v in value.items() if k not in clock_fields} != deterministic for value in values):
                raise ValueError("deterministic benchmark output differs across repeats")
            for field in clock_fields:
                sample = [value[field] for value in values]
                deterministic[field] = {"samples": sample, "median": statistics.median(sample),
                                        "minimum": min(sample), "maximum": max(sample)}
            row["methods"][method] = deterministic
        summary.append(row)
    write(output / "timing.json", {
        "status": "PASS", "repeats": repeats, "fresh_processes": len(trials),
        "case_records": len(trials) * len(cases), "python": platform.python_version(),
        "platform": platform.platform(), "cases": summary,
        "timing_scope": TIMING_SCOPE,
        "ordering": "One fresh process per method per repeat, rotated method order, sequential execution on one host.",
        "uncertainty": "Ranges are observed sample minima and maxima; no population confidence level is assigned.",
        "comparison": "Each timed complete semantic profile is compared exactly with the independently checked retained profile after the diagnosis clock stops.",
    })
    write(output / "timing-processes.json", trials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sizes", type=int, nargs="+", default=[2, 3, 4, 5, 6])
    parser.add_argument("--phase", choices=("all", "acquire", "analyze", "replay", "benchmark"), default="all")
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--child", choices=METHODS)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    if args.output is None:
        parser.error("--output is required")
    for size in args.sizes:
        fixtures.require_size(size)
    if len(set(args.sizes)) != len(args.sizes):
        parser.error("sizes must be distinct")
    try:
        if args.phase in ("all", "acquire"):
            acquire(args.output, args.sizes)
        if args.phase in ("all", "analyze"):
            analyze(args.output)
        if args.phase in ("all", "replay"):
            native_replay(args.output)
        if args.phase in ("all", "benchmark"):
            benchmark(args.output, args.repeats)
    except BaseException as error:
        args.output.mkdir(parents=True, exist_ok=True)
        write(args.output / "failure.json", {"phase": args.phase, "type": type(error).__name__,
              "message": str(error), "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
