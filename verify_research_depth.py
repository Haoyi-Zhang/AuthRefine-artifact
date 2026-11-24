#!/usr/bin/env python3
"""Read-only reconciliation of the current research records and finite results.

This verifies retained inputs, complete profiles, raw trials and observation
records. Finite diagnostic algorithms and independent finite oracles are run
again. Native application/ORM execution and the timing campaign are not run.
No retained result is modified; --output, when given, must name a new file.
The standard library and bundled artifact modules suffice.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import importlib.util
from itertools import product, zip_longest
import json
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
ARTIFACT = Path(__file__).resolve().parent
RESULTS = ARTIFACT / "results"
sys.path.insert(0, str(ARTIFACT / "src"))
sys.path.insert(0, str(ARTIFACT))
from policy import output as write_new_json


class CheckFailure(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate key in retained JSON")
            result[key] = value
        return result
    def nonfinite(value):
        raise CheckFailure("nonfinite retained JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def read(path):
    return decode(Path(path).read_bytes())


def plain(value):
    return decode(encoded(value))


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ARTIFACT / relative)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def verify_source_hashes(mapping):
    checked = {}
    for name, expected in mapping.items():
        path = (ARTIFACT / name).resolve()
        require(path.is_relative_to(ARTIFACT), "source hash path escapes artifact")
        actual = sha(path)
        if actual != expected and name == "benchmarks/stateful_family.py":
            # Only dataset locations changed when arranging the standalone
            # project. Reconstruct the measured source before comparing its
            # retained identity; any algorithmic or other byte change fails.
            recorded = path.read_bytes().replace(
                b"results/source-observer/comparisons.json",
                b"results/completion-20261118/direct-observer/run-4/comparisons.json").replace(
                b"results/native-session",
                b"results/research-depth-20261118/stateful-sequence/run-3")
            require(hashlib.sha256(recorded).hexdigest() == expected,
                    "measured benchmark source differs beyond data-path relocation")
        else:
            require(actual == expected, "current source differs from its recorded run: " + name)
        checked[name] = actual
    return checked


def support_profiles():
    directory = RESULTS / "support-indexed"
    summary, inputs = read(directory / "summary.json"), read(directory / "inputs.json")
    hashes = verify_source_hashes(summary["source_sha256"])
    audit = module("authrefine_verify_support_audit", "proofs/audit_support_indexed.py")
    require(inputs == {"policies": audit.policy_representatives(),
                       "machines": list(audit.target_machines())},
            "support audit inputs differ from the previously declared generated domain")
    policies, machines = inputs["policies"], inputs["machines"]
    require((len(policies), len(machines)) == (180, 128), "support audit domain cardinality")
    require(sha(directory / "inputs.json") == summary["inputs_sha256"], "support input digest")
    counts, strata, work, digest = Counter(), Counter(), Counter(), hashlib.sha256()
    pairs = binding_rows = replay_rows = 0
    with gzip.open(directory / "profiles.jsonl.gz", "rb") as stream:
        for data in stream:
            require(pairs < 23040, "extra support profile record")
            pi, mi = divmod(pairs, len(machines))
            row = decode(data)
            result = audit.compare_case(policies[pi], machines[mi])
            require(row == {"policy_id": pi, "machine_id": mi, **result},
                    f"retained support profile differs at pair {pi}/{mi}")
            digest.update(data)
            counts[result["classification"]] += 1
            strata.update(result["strata"])
            work.update(result["work_breakdown"])
            binding_rows += result["bindings"]
            replay_rows += sum(len(item["trace"] or []) for item in result["profiles"])
            pairs += 1
    require((pairs, binding_rows, replay_rows) == (23040, 43776, 18696), "support profile denominators")
    expected = {"policy_machine_pairs": pairs, "policy_semantic_representatives": len(policies),
                "machines_per_policy": len(machines), "binding_profiles_checked": binding_rows,
                "replay_rows_checked": replay_rows, "family_classifications": dict(counts),
                "binding_shortest_lengths": dict(strata), "implementation_work_breakdown": dict(work),
                "profiles_uncompressed_sha256": digest.hexdigest()}
    require(all(summary[key] == value for key, value in expected.items()), "support audit summary reconciliation")
    return {"status": "PASS", **expected, "inputs_sha256": sha(directory / "inputs.json"),
            "current_source_sha256": hashes,
            "scope": "Existing 23,040-pair domain rechecked with the current grouped algorithm, independent direct semantics/product search and full replay comparison; no new application sample."}


def caller_profiles():
    directory = RESULTS / "caller-family"
    summary, domains = read(directory / "summary.json"), read(directory / "domains.json")
    hashes = verify_source_hashes(summary["source_sha256"])
    audit = module("authrefine_verify_caller_audit", "proofs/protocol_family_audit.py")
    references, targets, callers = list(audit.reference_tables()), list(audit.target_tables()), list(audit.caller_tables())
    expected_domains = {"references": references, "targets": targets, "callers": callers,
                        "family": audit.FAMILY, "alphabet": audit.ALPHABET,
                        "initial_states": [0, 0, 0], "word_bound": 4}
    require(domains == plain(expected_domains), "caller-family audit domain differs")
    require((len(references), len(targets), len(callers)) == (9, 25, 9), "caller audit table cardinality")
    counts, strata, digest = Counter(), Counter(), hashlib.sha256()
    cases = classified = binding_rows = 0
    combinations = product(range(9), range(9), range(25), range(9))
    with gzip.open(directory / "cases.jsonl.gz", "rb") as stream:
        for ids, data in zip_longest(combinations, stream):
            require(ids is not None and data is not None, "missing or extra caller-family record")
            i, j, k, l = ids
            result = audit.compare_case(references[i], references[j], targets[k], callers[l])
            expected = {"reference_ids": [i, j], "target_id": k, "caller_id": l, **result}
            require(decode(data) == expected, f"caller-family record differs at {i}/{j}/{k}/{l}")
            digest.update(data)
            counts[result.get("classification", result.get("admission"))] += 1
            if result["status"] == "classified":
                classified += 1
                binding_rows += len(result["lengths"])
                strata.update("infinity" if length is None else str(length) for length in result["lengths"])
            cases += 1
    require((cases, classified, binding_rows) == (18225, 8910, 17820), "caller-family denominators")
    expected = {"instances": cases, "expected_instances": cases, "outcomes": dict(counts),
                "classified_binding_shortest_lengths": dict(strata),
                "cases_uncompressed_sha256": digest.hexdigest()}
    require(all(summary[key] == value for key, value in expected.items()), "caller-family summary reconciliation")
    return {"status": "PASS", **expected, "domains_sha256": sha(directory / "domains.json"),
            "classified_instances": classified,
            "classified_binding_results": binding_rows, "current_source_sha256": hashes,
            "scope": "Retained one-request finite domain rechecked by the current protocol-family algorithm and independent bounded-word table oracle; inactive and missing-edge instances have no classified binding rows."}


def cost_counts(result, payload):
    rows = payload
    return {"output_sha256": hashlib.sha256(encoded(rows)).hexdigest(),
            "output_bytes": len(encoded(rows)), "bindings": len(rows),
            "matching": sum(row["equivalent"] for row in rows),
            "failure_lengths": sorted({row["length"] for row in rows if not row["equivalent"]}),
            "semantic_steps": result["transition_evaluations"],
            "graph_nodes": result["graph_nodes"], "graph_edges": result["graph_edges"],
            "replay_steps": result["work_breakdown"].get("replay_steps", 0),
            **{name: result.get(name, 0) for name in (
                "support_queries", "family_projection_evaluations", "family_projection_coordinates",
                "index_memberships_created", "index_memberships_removed", "peak_cached_memberships")}}


def cost_records():
    directory = RESULTS / "family-cost"
    summary, inputs = read(directory / "summary.json"), read(directory / "inputs.json")
    profiles, trials = read(directory / "profiles.json"), read(directory / "trials.json")
    hashes = verify_source_hashes(summary["source_sha256"])
    bench = module("authrefine_verify_stateful_cost", "benchmarks/stateful_family.py")
    current_inputs = deepcopy(inputs)
    relocated = {
        "results/completion-20261118/direct-observer/run-4/comparisons.json":
            "results/source-observer/comparisons.json",
        "results/research-depth-20261118/stateful-sequence/run-3":
            "results/native-session",
    }
    for case in current_inputs:
        if case.get("provenance") in relocated:
            case["provenance"] = relocated[case["provenance"]]
    require(current_inputs == bench.cases(),
            "cost inputs differ from current specified controls/source tables beyond recorded data relocation")
    require(sha(directory / "inputs.json") == summary["input_sha256"], "cost input hash")
    methods, ids = list(bench.MODES), [case["id"] for case in inputs]
    require(len(ids) == len(set(ids)) == 38 and len(methods) == 4, "cost case/method cardinality")
    groups = Counter(case["group"] for case in inputs)
    require(groups == {"controlled": 34, "source-derived": 3, "source-derived-control": 1}, "cost cohort composition")
    require(summary["cases"] == 38 and summary["repeats"] == 7 and summary["methods"] == methods,
            "cost summary design")
    require([row["id"] for row in profiles] == ids, "complete cost output order or membership")
    expected_counts, totals = {}, {mode: Counter() for mode in methods}
    for case, stored in zip(inputs, profiles, strict=True):
        require(stored["sha256"] == hashlib.sha256(encoded(stored["profiles"])).hexdigest(),
                "complete cost output digest: " + case["id"])
        for mode in methods:
            result = bench.run_method(case, mode)
            rows = bench.output_rows(result)
            require(rows == stored["profiles"], "recomputed full cost output differs: " + case["id"] + "/" + mode)
            counts = cost_counts(result, rows)
            expected_counts[case["id"], mode] = counts
            totals[mode].update({name: value for name, value in counts.items() if type(value) is int})
            require(counts["matching"] == case["expected_matching"], "cost case expected matching family")
            require(counts["failure_lengths"] == ([] if case["expected_failure_length"] is None else
                                                   [case["expected_failure_length"]]), "cost case expected failure lengths")
    order = [(repeat, mode) for repeat in range(7)
             for mode in methods[repeat % 4:] + methods[:repeat % 4]]
    require(len(trials) == 28, "cost trial process count")
    timings = ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns")
    timed_records = 0
    for trial, (repeat, mode) in zip(trials, order, strict=True):
        require((trial["repeat"], trial["mode"], trial["exit_code"]) == (repeat, mode, 0),
                "rotated cost process order or exit code")
        raw_path = directory / f"trial-{repeat:02d}-{mode}.stdout.json"
        raw = read(raw_path)
        require(raw == {key: value for key, value in trial.items()
                        if key not in ("repeat", "process_wall_ns", "exit_code")}, "raw child result differs from trial aggregate")
        require((directory / f"trial-{repeat:02d}-{mode}.stderr.log").read_bytes() == b"", "cost child stderr is not empty")
        require([row["id"] for row in trial["records"]] == ids, "cost trial case order/membership")
        for row in trial["records"]:
            counts = expected_counts[row["id"], mode]
            require(all(row[key] == value for key, value in counts.items()), "raw cost scientific counters/output differ")
            require(all(type(row[field]) is int and row[field] >= 0 for field in timings), "invalid retained timing sample")
            timed_records += 1
        require(type(trial["process_wall_ns"]) is int and trial["process_wall_ns"] >= 0, "invalid process time")
    require([row["id"] for row in summary["records"]] == ids, "cost summary case order")
    medians = {}
    for case, row in zip(inputs, summary["records"], strict=True):
        require((row["group"], row["regime"]) == (case["group"], case["regime"]), "cost summary cohort label")
        require(set(row["methods"]) == set(methods), "cost summary methods")
        medians[case["id"]] = {}
        for mode in methods:
            values = [next(item for item in trial["records"] if item["id"] == case["id"])
                      for trial in trials if trial["mode"] == mode]
            require(len(values) == 7, "cost repeats per method/case")
            metrics = row["methods"][mode]
            require(all(metrics[key] == value for key, value in expected_counts[case["id"], mode].items()),
                    "cost summary scientific count")
            medians[case["id"]][mode] = {}
            for field in timings:
                samples = [value[field] for value in values]
                expected = {"median": statistics.median(samples), "min": min(samples),
                            "max": max(samples), "samples": samples}
                require(metrics[field] == expected, "cost summary median/range/samples differ: " + case["id"] + "/" + mode + "/" + field)
                medians[case["id"]][mode][field] = expected["median"]
    require(timed_records == 38 * 4 * 7, "cost timed-record denominator")
    return {"status": "PASS", "cases": 38, "methods": methods, "repeats": 7,
            "process_trials": len(trials), "timed_case_records": timed_records,
            "recomputed_method_case_results": len(expected_counts), "recomputed_medians": 38 * 4 * 3,
            "cohort": dict(groups),
            "complete_output_sha256_by_case": {row["id"]: row["sha256"] for row in profiles},
            "scientific_counts_by_case": {
                case["id"]: {mode: expected_counts[case["id"], mode] for mode in methods}
                for case in inputs},
            "scientific_count_sums_per_method": {mode: dict(value) for mode, value in totals.items()},
            "input_sha256": sha(directory / "inputs.json"),
            "timing_medians_ns": medians, "current_source_sha256": hashes,
            "scope": "Saved raw child trials reaggregated; finite algorithms rerun for complete output and scientific-counter equality. No new timing campaign or native source execution."}


def expected_session(before, request, control, increase_seconds, fixtures):
    """Independent equations for all retained fixture fields, without ORM calls."""
    before = deepcopy(before)
    after = deepcopy(before)
    token = fixtures.token_for(request[1], request[2])
    selected = next((row for row in before if row["token"] == token), None)
    selected_record = None
    returned = None
    if request[2] == "lookup":
        if selected is not None:
            selected_record = {name: selected[name] for name in ("id", "token", "user_id")}
            expiry = datetime.fromisoformat(selected["expiry_date"])
            maximum = datetime.fromisoformat(selected["max_expiry_date"])
            if expiry > fixtures.NOW and maximum > fixtures.NOW:
                returned = selected["user_id"]
                if increase_seconds and expiry - fixtures.NOW < timedelta(seconds=increase_seconds):
                    for row in after:
                        if row["id"] == selected["id"]:
                            row["expiry_date"] = (expiry + timedelta(seconds=increase_seconds)).isoformat()
    else:
        require(request[2] == "remove" and increase_seconds is None, "invalid retained lifecycle operation")
        if control != "omit_delete":
            after = [row for row in before if row["token"] != token]
    return {"request": list(request), "token_argument": token,
            "increase_seconds": increase_seconds, "returned_user_id": returned,
            "selected_record": selected_record,
            "decision": "allow" if request[2] == "remove" or returned is not None else "deny",
            "before_state": fixtures.mask(before), "after_state": fixtures.mask(after),
            "before_rows": before, "after_rows": after,
            "removed_ids": sorted({row["id"] for row in before} - {row["id"] for row in after}),
            "store_changed": before != after}


def session_records():
    from source_study.stateful_sequence import fixtures, source, collect
    from source_study.stateful_sequence.diagnose import diagnose, contract_step
    directory = RESULTS / "native-session"
    summary, runtime = read(directory / "summary.json"), read(directory / "runtime.json")
    hashes = verify_source_hashes(runtime["source_sha256"])
    require({"src/family_diagnosis.py", "src/protocol_profile.py", "src/checker.py"} <= set(hashes),
            "native runtime does not pin the current diagnostic core")
    extras = sorted(str(path.relative_to(ARTIFACT)) for path in (ARTIFACT / "source_study/stateful_sequence").glob("*.py")
                    if str(path.relative_to(ARTIFACT)) not in hashes)
    require(extras == ["source_study/stateful_sequence/export_profile_inputs.py"],
            "unexpected code absent from the retained native run's source manifest")
    for name, expected in runtime["output_sha256"].items():
        require(Path(name).name == name and sha(directory / name) == expected, "native retained output hash: " + name)
    scientific_names = ("fixtures.json", "native-observations.json", "interpreted-observations.json",
                        "diagnosis.json", "native-witness-replay.json", "summary.json")
    identities = {}
    for name in scientific_names:
        current = directory / name
        identities[name] = sha(current)
    native, interpreted = read(directory / "native-observations.json"), read(directory / "interpreted-observations.json")
    require(native == interpreted, "native/interpreted session records differ")
    require(read(directory / "fixtures.json") == fixtures.document(), "current session fixtures differ")
    require(native["source_manifests"] == [source.load(None)[3], source.load("omit_delete")[3]],
            "session selected-source manifests differ")
    alphabet, initial_rows = fixtures.alphabet(), fixtures.serialized_rows(fixtures.rows())
    edge_counts, prefixes, graph_states = {}, 0, {}
    for name in ("baseline", "omit_delete"):
        graph = native[name]
        require(graph["machine"] == collect.machine(graph), "session table does not reconstruct from raw edges")
        seen_edges = set()
        local_prefixes = 0
        for edge in graph["edges"]:
            key = (edge["from_state"], edge["input_index"])
            require(key not in seen_edges, "duplicate session edge")
            seen_edges.add(key)
            rows = deepcopy(initial_rows)
            require(len(edge["prefix"]) == len(edge["prefix_observations"]), "session prefix row count")
            for index, observed in zip(edge["prefix"], edge["prefix_observations"], strict=True):
                expected = expected_session(rows, alphabet[index], name, None, fixtures)
                require(observed == expected, "session prefix differs from direct fixture equations")
                rows = expected["after_rows"]
                local_prefixes += 1
            require(fixtures.mask(rows) == edge["from_state"], "session prefix reaches the wrong state")
            expected = expected_session(rows, alphabet[edge["input_index"]], name, None, fixtures)
            require(edge["observation"] == expected, "session edge differs from direct fixture equations")
        require(len(seen_edges) == len(graph["states"]) * len(alphabet), "session graph incomplete")
        require(graph["prefix_steps"] == local_prefixes and graph["source_operations"] == local_prefixes + len(seen_edges),
                "session prefix/source-operation accounting")
        reached, waiting = {graph["machine"]["initial"]}, deque([graph["machine"]["initial"]])
        while waiting:
            node = waiting.popleft()
            for _, following in graph["machine"]["transitions"][node]:
                if following not in reached:
                    reached.add(following)
                    waiting.append(following)
        require(len(reached) == len(graph["states"]), "unreachable session table row")
        edge_counts[name], graph_states[name] = len(seen_edges), len(reached)
        prefixes += local_prefixes
    expiry_fixtures = list(fixtures.expiry_inputs())
    require(len(native["expiry_boundaries"]) == len(expiry_fixtures) == 90, "session expiry denominator")
    for record, fixture in zip(native["expiry_boundaries"], expiry_fixtures, strict=True):
        rows = fixtures.serialized_rows(fixtures.rows(fixture["expiry_a_seconds"], fixture["maximum_a_seconds"]))
        expected = expected_session(rows, fixture["request"], "baseline", fixture["increase_seconds"], fixtures)
        require(record == {"id": fixture["id"], "observation": expected}, "expiry boundary differs from direct fixture equations")
    diagnosis = diagnose(native)
    require(diagnosis == read(directory / "diagnosis.json"), "session family diagnosis differs from current finite algorithms/oracles")
    witness_records = read(directory / "native-witness-replay.json")
    expected_replays = []
    for name, profile in diagnosis["profiles"].items():
        for mode, entries in (("full", profile["binding_profile"]["profiles"]),
                              ("decision_only", [{"binding": row["binding"], **row["decision_only"]}
                                                 for row in profile["independent"]])):
            for entry in entries:
                if entry["equivalent"]:
                    continue
                rows, reference = deepcopy(initial_rows), 3
                observations = []
                for index in entry["indices"]:
                    request = alphabet[index]
                    actual = expected_session(rows, request, name, None, fixtures)
                    decision, reference = contract_step(reference, request, entry["binding"])
                    same = decision == actual["decision"] and (mode == "decision_only" or reference == actual["after_state"])
                    observations.append({"observation": actual, "reference_decision": decision,
                                         "reference_state": reference, "equal": same})
                    rows = actual["after_rows"]
                require(observations and all(row["equal"] for row in observations[:-1]) and not observations[-1]["equal"],
                        "native witness does not first differ at its final row")
                expected_replays.append({"profile": name, "mode": mode, "binding": entry["binding"],
                                         "observations": observations})
    require(witness_records == expected_replays, "retained native witnesses differ from direct field/reference equations")
    witness_operations = sum(len(row["observations"]) for row in witness_records)
    values = {"baseline_reachable_states": graph_states["baseline"],
              "baseline_paired_edges": edge_counts["baseline"], "control_reachable_states": graph_states["omit_delete"],
              "control_paired_edges": edge_counts["omit_delete"], "paired_expiry_boundary_inputs": len(expiry_fixtures),
              "unmodified_paired_total": edge_counts["baseline"] + len(expiry_fixtures),
              "control_paired_total": edge_counts["omit_delete"],
              "paired_total": sum(edge_counts.values()) + len(expiry_fixtures),
              "additional_prefix_operations_per_arm": prefixes,
              "source_acquisition_operations_per_arm": prefixes + sum(edge_counts.values()) + len(expiry_fixtures),
              "extra_native_witness_runs": len(witness_records), "extra_native_witness_operations": witness_operations}
    require((values["unmodified_paired_total"], values["control_paired_total"]) == (130, 10), "native source/control denominators")
    require(all(summary[key] == value for key, value in values.items()), "session summary counts")
    return {"status": "PASS", **values, "paired_disagreements": 0,
            "scientific_payloads_sha256": identities, "current_recorded_source_sha256": hashes,
            "later_unlisted_helper": {name: sha(ARTIFACT / name) for name in extras},
            "scope": "Retained native/interpreted fields, prefixes, expiry boundaries and native witness records checked by direct fixture equations; finite diagnoses rerun. No native execution. The later export helper is not claimed to have been in the earlier run."}


def historical_records():
    from source_study.historical_h19.matrix import compare_versions
    directory = RESULTS / "published-patch"
    recomputed = compare_versions(directory)
    require(recomputed == read(directory / "summary.json"), "H19 matrix summary differs from offline raw-record verifier")
    metadata = invocations = 0
    outcomes = Counter()
    for version in ("1.16.0", "1.34.0"):
        raw = read(directory / ("orm-" + version) / "native-observations.json")
        metadata += len(raw["selection_observations"])
        endpoints = raw["selection_observations"] + raw["filter_observations"]
        invocations += len(endpoints)
        outcomes.update(row["endpoint"]["outcome"] for row in endpoints)
    require((metadata, invocations, outcomes["return"], outcomes["exception"]) == (180, 210, 198, 12),
            "H19 metadata/endpoint raw-record denominators")
    return {"status": "PASS", "metadata_pairs": metadata, "complete_get_all_invocations": invocations,
            "endpoint_returns": outcomes["return"], "endpoint_exceptions": outcomes["exception"],
            "change_counts": recomputed["change_counts"], "orm_versions": recomputed["orm_versions"],
            "fixture_sha256": recomputed["fixture_sha256"],
            "scope": "Existing offline H19 verifier checks raw readbacks, metadata/endpoint equations, pinned source and matrix equality. Both recorded ORM profiles are reconciled without loading or executing either ORM."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional new JSON receipt; existing files are never replaced")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        print(json.dumps({"status": "FAIL", "error": "refusing to overwrite output receipt"}))
        return 1
    results = {}
    for name, check in (("support_indexed", support_profiles), ("caller_family", caller_profiles),
                        ("stateful_cost", cost_records), ("native_session_records", session_records),
                        ("historical_h19_records", historical_records)):
        try:
            results[name] = check()
        except Exception as error:
            results[name] = {"status": "FAIL", "error_type": type(error).__name__, "error": str(error)}
    passed = all(row["status"] == "PASS" for row in results.values())
    report = {"status": "PASS" if passed else "FAIL", "checks": results,
              "verifier_sha256": sha(Path(__file__)),
              "scope": "Read-only reconciliation of the current research release. Finite computations are rerun; retained native executions and timing samples are verified as records, not described as new source executions."}
    if args.output is not None:
        try:
            write_new_json(args.output, report)
        except (OSError, ValueError) as error:
            report["status"] = "FAIL"
            report["output_error"] = {"error_type": type(error).__name__, "error": str(error)}
            passed = False
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
