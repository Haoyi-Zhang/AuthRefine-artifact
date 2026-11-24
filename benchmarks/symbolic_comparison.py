"""Compare complete diagnostic outputs with explicit and symbolic sharing.

All implementations receive the same target, legal family and optional caller.
Every timed result is compared with the retained complete canonical output
after its diagnosis clock stops. The campaign never overwrites older timings.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from benchmarks.stateful_family import output_rows, search_family
from checker import ensure
from extensions import binding_profile
from family_diagnosis import support_indexed_profile
from protocol_profile import protocol_binding_profile
from protocol_grouped import support_indexed_protocol_profile
from symbolic_family import symbolic_family_profile

METHODS = ("per-binding-product", "per-binding-target", "scan", "support-indexed",
           "finite-domain", "cudd")
COMMON_METHODS = METHODS[2:]
TIMES = ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns")
COUNTERS = ("output_sha256", "output_bytes", "bindings", "matching", "failure_lengths",
            "diagnostic_reference_calls", "replay_steps", "graph_cells", "symbolic_nodes",
            "symbolic_peak_nodes", "symbolic_conditional_operations", "symbolic_predicates",
            "symbolic_cache_hits", "symbolic_regions", "family_relation_nodes",
            "family_relation_coordinates", "support_queries", "index_memberships_created",
            "index_memberships_removed")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write_gzip(path, value):
    path.write_bytes(gzip.compress(encoded(value), mtime=0))


def source_identities():
    names = ["benchmarks/symbolic_comparison.py", "benchmarks/stateful_family.py"] + [
        "src/" + name for name in ("symbolic_family.py", "symbolic.py", "checker.py", "extensions.py",
                                  "protocol_profile.py", "protocol_grouped.py", "family_diagnosis.py")]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def tasks(include_policy_store=True):
    previous = ROOT / "results/family-cost"
    saved = {row["id"]: row["profiles"] for row in read(previous / "profiles.json")}
    result = []
    for case in read(previous / "inputs.json"):
        result.append({"id": "family-cost/" + case["id"], "case": case["id"],
                       "cohort": "family-cost", "group": case["group"],
                       "regime": case["regime"], "caller": "total", "protocol": None,
                       "policy": case["policy"], "machine": case["machine"],
                       "family": case.get("family"), "expected": saved[case["id"]]})
    cohorts = [("session-correspondence", ROOT / "results/session-correspondence/inputs.json.gz")]
    if include_policy_store:
        cohorts.append(("native-policy-store", ROOT / "results/native-policy-store/inputs.json.gz"))
    for cohort, source in cohorts:
        for case in read(source):
            for caller, protocol in [("total", None), *case["callers"].items()]:
                key = "support-indexed" if protocol is None else "protocol-grouped/" + caller
                result.append({"id": cohort + "/" + case["id"] + "/" + caller,
                               "case": case["id"], "cohort": cohort,
                               "group": case.get("arm", "native"), "regime": case.get("arm", "native"),
                               "caller": caller, "protocol": protocol,
                               "policy": case["policy"], "machine": case["machine"],
                               "family": case["family"], "expected": case["expected"][key]})
    ensure(len({row["id"] for row in result}) == len(result), "unique comparison task identifiers")
    return result


def methods(task):
    return METHODS if task["protocol"] is None else COMMON_METHODS


def evaluate(task, method):
    policy, machine, family, caller = (task[k] for k in ("policy", "machine", "family", "protocol"))
    if method in ("finite-domain", "cudd"):
        return symbolic_family_profile(policy, machine, family=family, protocol=caller, backend=method)
    if method in METHODS[:2]:
        ensure(caller is None, "per-binding total-table method received a caller")
        return search_family(policy, machine, method, family=family)
    if caller is not None:
        function = protocol_binding_profile if method == "scan" else support_indexed_protocol_profile
        return function(policy, machine, caller, family=family)
    function = binding_profile if method == "scan" else support_indexed_profile
    return function(policy, machine, family=family)


def prepare_backend(method):
    # Import cost is common worker preparation, before any diagnosis clock.
    if method == "cudd":
        import dd.cudd
        ensure(metadata.version("dd") == "0.6.0", "use the supplied CUDD comparison dependency")


def worker(method, cohort):
    prepare_backend(method)
    records = []
    for task in cohort:
        if method not in methods(task):
            continue
        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = evaluate(task, method)
        diagnosis_wall_ns, diagnosis_cpu_ns = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
        canonical = output_rows(result)
        ensure(canonical == task["expected"], "timed complete output differs: " + task["id"])
        start = time.perf_counter_ns()
        payload = encoded(canonical)
        serialization_ns = time.perf_counter_ns() - start
        symbolic = result.get("symbolic", {})
        work = result.get("work_breakdown", {})
        records.append({"id": task["id"], "diagnosis_wall_ns": diagnosis_wall_ns,
                        "diagnosis_cpu_ns": diagnosis_cpu_ns, "serialization_ns": serialization_ns,
                        "output_sha256": hashlib.sha256(payload).hexdigest(), "output_bytes": len(payload),
                        "bindings": len(canonical), "matching": sum(row["equivalent"] for row in canonical),
                        "failure_lengths": sorted({row["length"] for row in canonical if not row["equivalent"]}),
                        "diagnostic_reference_calls": result.get("transition_evaluations", 0),
                        "replay_steps": work.get("replay_steps", 0),
                        "graph_cells": result.get("graph_cells_inspected", result.get("graph_edges", work.get("graph_edges", 0))),
                        "symbolic_nodes": symbolic.get("nodes", 0),
                        "symbolic_peak_nodes": symbolic.get("peak_nodes", symbolic.get("nodes", 0)),
                        "symbolic_conditional_operations": symbolic.get("conditional_operations", 0),
                        "symbolic_predicates": symbolic.get("predicate_constructions", 0),
                        "symbolic_cache_hits": symbolic.get("predicate_cache_hits", 0),
                        "symbolic_regions": symbolic.get("first_bad_regions", 0),
                        "family_relation_nodes": work.get("family_relation_nodes", 0),
                        "family_relation_coordinates": work.get("family_relation_coordinates", 0),
                        "support_queries": result.get("support_queries", 0),
                        "index_memberships_created": result.get("index_memberships_created", 0),
                        "index_memberships_removed": result.get("index_memberships_removed", 0)})
    return {"method": method, "records": records, "python": sys.version,
            "platform": platform.platform(), "complete_outputs_compared": True,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "dd_package": metadata.version("dd") if method == "cudd" else None}


def summarize(cohort, trials, repeats):
    ensure(type(repeats) is int and 3 <= repeats <= 15, "repeat count in 3..15")
    ensure(len(trials) == repeats * len(METHODS), "complete method/repeat process matrix")
    matrix = {}
    for trial in trials:
        identity = (trial["repeat"], trial["method"])
        ensure(identity not in matrix and 0 <= trial["repeat"] < repeats and trial["method"] in METHODS,
               "unique valid method/repeat process")
        ensure(trial["exit_code"] == 0 and trial["complete_outputs_compared"] is True,
               "successful complete-output worker")
        selected = [task for task in cohort if trial["method"] in methods(task)]
        expected_ids = [task["id"] for task in selected]
        ensure([row["id"] for row in trial["records"]] == expected_ids, "exact timed task order and denominator")
        for task, row in zip(selected, trial["records"]):
            expected = task["expected"]
            ensure(row["output_sha256"] == digest(expected) and row["output_bytes"] == len(encoded(expected)),
                   "timed complete output identity")
            ensure(row["bindings"] == len(expected) and row["matching"] == sum(v["equivalent"] for v in expected),
                   "timed family denominator")
            ensure(row["failure_lengths"] == sorted({v["length"] for v in expected if not v["equivalent"]}),
                   "timed shortest-failure strata")
            for field in TIMES:
                ensure(type(row[field]) is int and row[field] >= 0, "nonnegative integer timing")
            for field in COUNTERS:
                if field in ("output_sha256", "failure_lengths"):
                    continue
                ensure(type(row[field]) is int and row[field] >= 0,
                       "nonnegative integer work/output counter: " + field)
        matrix[identity] = {row["id"]: row for row in trial["records"]}
    rows = []
    for task in cohort:
        row = {key: task[key] for key in ("id", "case", "cohort", "group", "regime", "caller")}
        row["methods"] = {}
        for method in methods(task):
            values = [matrix[(repeat, method)][task["id"]] for repeat in range(repeats)]
            entry = {}
            for field in COUNTERS:
                observed = [value[field] for value in values]
                # CUDD's automatic reordering and garbage collection may change
                # manager node counts without changing any semantic output.
                if field in ("symbolic_nodes", "symbolic_peak_nodes"):
                    entry[field] = {"min": min(observed), "max": max(observed), "samples": observed}
                else:
                    ensure(all(value == observed[0] for value in observed), "stable scientific work: " + field)
                    entry[field] = observed[0]
            for field in TIMES:
                sample = [value[field] for value in values]
                entry[field] = {"median": statistics.median(sample), "min": min(sample),
                                "max": max(sample), "samples": sample}
            row["methods"][method] = entry
        rows.append(row)
    return {"status": "PASS", "tasks": len(cohort), "case_method_pairs": sum(len(methods(task)) for task in cohort),
            "repeats": repeats, "processes": len(trials), "timed_task_records": sum(len(t["records"]) for t in trials),
            "cohort_tasks": {name: sum(t["cohort"] == name for t in cohort) for name in sorted({t["cohort"] for t in cohort})},
            "methods": list(METHODS), "records": rows,
            "output_contract": "all legal members, canonical first shortest word, every fixed-binding replay field",
            "timing_contract": "schema/family validation, relation/index construction, complete graph admission, diagnosis and all individual replays",
            "outside_diagnosis_clock": ["process startup", "module imports", "input decoding", "comparison against expected output", "output serialization"],
            "counter_interpretation": "Concrete reference calls, finite-domain recursive ITE invocations and CUDD ITE API calls are different units; timing compares complete tasks.",
            "source_reuse": "The earlier two-session targets also occur in the expanded session cohort. Caller languages and initial files are tasks on the same source interfaces, not additional applications.",
            "uncertainty": "Seven sequential rotated repetitions by default; ranges are observed minima/maxima on this host, not confidence intervals."}


def run(output, repeats):
    ensure(not output.exists(), "fresh comparison output required")
    ensure(3 <= repeats <= 15, "repeat count in 3..15")
    prepare_backend("cudd")
    output.mkdir(parents=True)
    identities = source_identities()
    start = time.perf_counter_ns()
    cohort = tasks()
    setup_ns = time.perf_counter_ns() - start
    write_gzip(output / "inputs.json.gz", [{k: v for k, v in task.items() if k != "expected"} for task in cohort])
    write_gzip(output / "profiles.json.gz", [{"id": task["id"], "profiles": task["expected"]} for task in cohort])
    payload = encoded(cohort)
    trials = []
    trial_dir = output / "trials"
    trial_dir.mkdir()
    for repeat in range(repeats):
        order = METHODS[repeat % len(METHODS):] + METHODS[:repeat % len(METHODS)]
        for method in order:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", method]
            start = time.perf_counter_ns()
            process = subprocess.run(command, input=payload, capture_output=True, timeout=600,
                                     env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            process_ns = time.perf_counter_ns() - start
            stem = f"repeat-{repeat:02d}-{method}"
            (trial_dir / (stem + ".stdout.json")).write_bytes(process.stdout)
            (trial_dir / (stem + ".stderr.txt")).write_bytes(process.stderr)
            ensure(process.returncode == 0, "comparison worker failed: " + stem)
            trial = json.loads(process.stdout)
            ensure(trial["method"] == method, "worker method identity")
            trial.update(repeat=repeat, exit_code=process.returncode, process_wall_ns=process_ns,
                         stdout="trials/" + stem + ".stdout.json", stderr="trials/" + stem + ".stderr.txt")
            trials.append(trial)
        print(f"completed comparison repetition {repeat + 1}/{repeats}", flush=True)
    ensure(source_identities() == identities, "comparison source changed during the campaign")
    summary = summarize(cohort, trials, repeats)
    (output / "trials.json").write_bytes(encoded(trials))
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    environment = {"source_identities": identities, "input_preparation_wall_ns": setup_ns,
                   "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                   "packages": {name: metadata.version(name) for name in ("dd", "astutils", "networkx", "ply", "setuptools")},
                   "campaign_sources_unchanged": True}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("status", "tasks", "processes", "timed_task_records")}))


def verify(output):
    inputs = read(output / "inputs.json.gz")
    profiles = read(output / "profiles.json.gz")
    ensure([v["id"] for v in inputs] == [v["id"] for v in profiles], "input/profile alignment")
    cohort = [{**task, "expected": row["profiles"]} for task, row in zip(inputs, profiles)]
    expected_tasks = tasks()
    ensure(cohort == expected_tasks, "comparison cohort differs from its retained scientific inputs")
    trials = read(output / "trials.json")
    for trial in trials:
        raw = read(output / trial["stdout"])
        ensure(all(trial[key] == value for key, value in raw.items()), "raw worker result differs")
        ensure((output / trial["stderr"]).read_text() == "", "worker stderr is not empty")
    retained = read(output / "summary.json")
    actual = summarize(cohort, trials, retained["repeats"])
    ensure(actual == retained, "derived comparison summary differs")
    environment = read(output / "environment.json")
    ensure(environment["source_identities"] == source_identities(), "comparison implementation changed")
    return {k: actual[k] for k in ("status", "tasks", "case_method_pairs", "repeats", "processes", "timed_task_records")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--worker", choices=METHODS)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, json.load(sys.stdin))))
    elif args.verify:
        print(json.dumps(verify(args.verify), indent=2))
    else:
        if args.output is None:
            parser.error("--output is required")
        run(args.output, args.repeats)
