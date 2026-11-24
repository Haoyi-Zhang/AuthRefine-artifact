#!/usr/bin/env python3
"""Recompute session-study tables and check them against retained raw records.

No installed ORM is needed. This reads native observations; it does not claim
to execute the source again. With --write-tables, only the two named CSV tables
are written. Without that flag the command checks existing tables read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
from pathlib import Path
import statistics
import sys

ART = Path(__file__).resolve().parents[2]
for directory in (ART, ART / "src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
sys.dont_write_bytecode = True

from source_study.session_correspondence import fixtures, oracle
from source_study.session_correspondence.run import (
    ACQUISITION_SCOPE, METHODS, TIMING_SCOPE, check_native_cells, read)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_bytes(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def verify(results):
    inputs = read(results / "inputs.json.gz")
    native = read(results / "native-observations.json.gz")
    diagnosis = read(results / "diagnosis.json")
    profiles = read(results / "profiles.json.gz")
    timing = read(results / "timing.json")
    processes = read(results / "timing-processes.json")
    replay = read(results / "native-witness-replay.json.gz")
    replay_summary = read(results / "native-replay-summary.json")
    acquisition = read(results / "acquisition.json")
    native_by_size = {row["sessions"]: row for row in native}
    input_by_id = {row["id"]: row for row in inputs}
    summary_by_id = {row["id"]: row for row in diagnosis["cases"]}
    profile_by_id = {row["id"]: row for row in profiles}
    replay_by_id = {row["id"]: row for row in replay}
    require(len(input_by_id) == len(inputs) == len(summary_by_id) == len(profile_by_id) == len(replay_by_id),
            "case identifiers are duplicate or incomplete")
    require(set(input_by_id) == set(summary_by_id) == set(profile_by_id) == set(replay_by_id),
            "case identifiers differ among retained artifacts")
    require(acquisition["timing_scope"] == ACQUISITION_SCOPE and timing["timing_scope"] == TIMING_SCOPE,
            "timing scope is stale")
    require(acquisition["total_acquisition_wall_ns"] == sum(row["acquisition_wall_ns"] for row in acquisition["records"]),
            "acquisition total differs from its measured cases")
    scientific_rows = []
    checked_native_records = checked_bindings = replay_bindings = replay_steps = distinct_words = 0
    anchored_profiles = anchored_bindings = 0
    for case in inputs:
        identifier, size, arm = case["id"], case["sessions"], case["arm"]
        graph = native_by_size[size][arm]
        summary = summary_by_id[identifier]
        checked_native_records += check_native_cells(size, graph, arm == "omit-delete")
        require(case["machine"] == graph["machine"], "input machine differs from its native cells")
        require(case["policy"] == fixtures.contract(size), "input contract differs from supplied fixture contract")
        require(case["family"] == fixtures.family(size), "supplied family was changed or completed")
        require(case["callers"] == fixtures.callers(case["machine"]["alphabet"]), "caller input changed")
        require(case["expected"] == profile_by_id[identifier]["profiles"], "retained complete profiles differ")
        selected = {(graph["states"].index(edge["from_state"]), edge["input_index"]):
                    None if edge["observation"]["selected_record"] is None else edge["observation"]["selected_record"]["id"]
                    for edge in graph["edges"]}
        for caller, records in profile_by_id[identifier]["selected_identity_profiles"].items():
            expected = [oracle.profile(size, case["machine"], binding, case["callers"][caller], selected)
                        for binding in case["family"]]
            expected = [{key: row[key] for key in ("binding", "equivalent", "length", "indices")} for row in expected]
            require(records == expected, "selected-identity profile differs from the native row observations")
            require(summary["selected_identity_matching"][caller] == sum(row["equivalent"] for row in expected),
                    "selected-identity matching count differs")
        for method, rows in case["expected"].items():
            caller = case["callers"][method.split("/")[1]] if "/" in method else None
            for binding, row in zip(case["family"], rows):
                # Recompute the independent answer, including all replay fields.
                require(row == oracle.profile(size, case["machine"], binding, caller),
                        "retained profile disagrees with direct-equation product search")
                checked_bindings += 1
            require(len(rows) == len(case["family"]), "incomplete per-binding profile")
        coverage = Counter(tuple(row["indices"]) for row in case["expected"]["shared-target"] if not row["equivalent"])
        expected_coverage = [{"indices": list(word), "requests": [case["machine"]["alphabet"][index] for index in word],
                              "excluded_bindings": count} for word, count in sorted(coverage.items())]
        require(summary["witness_coverage"] == expected_coverage, "witness multiplicities differ")
        physical = {tuple(row["indices"]): row for row in replay_by_id[identifier]["words"]}
        require(set(physical) == set(coverage), "native witness words are incomplete or extra")
        for row in case["expected"]["shared-target"]:
            if not row["equivalent"]:
                oracle.check_native_witness(size, row["binding"], row["indices"], physical[tuple(row["indices"])]["observations"])
                replay_bindings += 1
        for word, count in coverage.items():
            require(physical[word]["excluded_bindings_checked"] == count, "native word coverage differs")
            distinct_words += 1
            replay_steps += len(physical[word]["observations"])
        for anchored in profile_by_id[identifier]["anchored_family_profiles"]:
            positions = [i for i, binding in enumerate(case["family"])
                         if all(binding[name] == value for name, value in anchored["anchor"].items())]
            for method, rows in anchored["profiles"].items():
                require(rows == [case["expected"][method][i] for i in positions],
                        "anchored family does not preserve exact fixed-binding answers")
                anchored_profiles += 1
                anchored_bindings += len(rows)
            retained = next(row for row in summary["anchored_families"] if row["name"] == anchored["name"])
            matching = sum(row["equivalent"] for row in anchored["profiles"]["support-indexed"])
            require(retained["anchor"] == anchored["anchor"] and retained["family_members"] == len(positions)
                    and retained["matching"] == matching and retained["excluded"] == len(positions) - matching,
                    "anchored family summary differs from its complete profile")
        scientific_rows.append({
            "case": identifier, "sessions": size, "arm": arm, "native_states": len(graph["states"]),
            "request_symbols": len(graph["machine"]["alphabet"]), "native_edges": len(graph["edges"]),
            "prefix_operations": graph["prefix_operations"], "supplied_bijections": len(case["family"]),
            "cartesian_combinations": size ** size,
            "unrestricted_matching": summary["caller_outcomes"]["unrestricted"]["matching"],
            "lookup_only_matching": summary["caller_outcomes"]["lookup-only"]["matching"],
            "one_removal_matching": summary["caller_outcomes"]["one-removal"]["matching"],
            "shortest_excluded_length": summary["caller_outcomes"]["unrestricted"]["shortest_excluded_length"],
            "distinct_exclusion_words": len(coverage), "excluded_bindings": sum(coverage.values()),
        })
    require(checked_bindings == diagnosis["complete_profile_comparisons"], "full-profile comparison count differs")
    require(anchored_profiles == diagnosis["anchored_family_profiles"] and anchored_bindings == diagnosis["anchored_binding_comparisons"],
            "anchored comparison counts differ")
    require((distinct_words, replay_steps, replay_bindings) == (
        replay_summary["distinct_native_word_runs"], replay_summary["native_operations"], replay_summary["excluded_binding_replays_checked"]),
        "native replay totals differ")
    require(len(processes) == timing["fresh_processes"] == timing["repeats"] * len(METHODS),
            "timing process count differs")
    expected_order = [(repeat + 1, method) for repeat in range(timing["repeats"])
                      for method in METHODS[repeat % len(METHODS):] + METHODS[:repeat % len(METHODS)]]
    require([(trial["repeat"], trial["method"]) for trial in processes] == expected_order,
            "recorded process order is not the declared rotation")
    clock_fields = ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns")
    for trial in processes:
        path = results / "timing-trials" / f"repeat-{trial['repeat']}-{trial['method'].replace('/', '-')}.json"
        raw = read(path)
        require(raw == {key: value for key, value in trial.items() if key not in ("repeat", "process_wall_ns")},
                "raw process stdout differs from the combined timing record")
        require([r["id"] for r in trial["records"]] == [c["id"] for c in inputs], "timed cohort/order differs")
        require(all(type(row[field]) is int and row[field] >= 0 for row in trial["records"] for field in clock_fields),
                "invalid timing unit or value")
    timing_rows = []
    for case in timing["cases"]:
        require(case["id"] in input_by_id, "unknown timed case")
        for method in METHODS:
            values = [next(row for row in trial["records"] if row["id"] == case["id"])
                      for trial in processes if trial["method"] == method]
            require(len(values) == timing["repeats"], "timing repeat is missing")
            observed = case["methods"][method]
            for field in clock_fields:
                sample = [row[field] for row in values]
                expected = {"samples": sample, "median": statistics.median(sample),
                            "minimum": min(sample), "maximum": max(sample)}
                require(observed[field] == expected, "timing summary differs from raw repeat values")
            fixed = {k: v for k, v in observed.items() if k not in clock_fields}
            require(all({k: v for k, v in row.items() if k not in clock_fields} == fixed for row in values),
                    "work counts changed across repeats")
            require(fixed["complete_output_equal"] is True, "timed semantic equality did not pass")
            require(all(fixed[k] == v for k, v in summary_by_id[case["id"]]["work"][method].items()),
                    "timed work differs from independent-validation execution")
            row = {"case": case["id"], "sessions": case["sessions"], "arm": case["arm"], "method": method,
                   "bindings": fixed["bindings"], "matching": fixed["matching"],
                   "semantic_steps": fixed["semantic_steps"], "replay_steps": fixed["replay_steps"],
                   "output_bytes": fixed["output_bytes"], "repeats": timing["repeats"]}
            for field, prefix in (("diagnosis_wall_ns", "wall"), ("diagnosis_cpu_ns", "cpu"), ("serialization_ns", "serialization")):
                for statistic in ("median", "minimum", "maximum"):
                    row[f"{prefix}_{statistic}_ms"] = f"{observed[field][statistic] / 1_000_000:.6f}"
            timing_rows.append(row)
    require(len(processes) * len(inputs) == timing["case_records"], "timing case count differs")
    files = {"case-summary.csv": csv_bytes(scientific_rows, list(scientific_rows[0])),
             "timing-summary.csv": csv_bytes(timing_rows, list(timing_rows[0]))}
    return files, {"status": "PASS", "native_rich_records": checked_native_records,
                   "independent_binding_comparisons": checked_bindings,
                   "anchored_profiles": anchored_profiles, "anchored_binding_comparisons": anchored_bindings,
                   "native_word_runs": distinct_words, "native_replay_operations": replay_steps,
                   "native_replay_binding_checks": replay_bindings,
                   "timing_processes": len(processes), "timing_case_records": timing["case_records"],
                   "table_rows": {name: len(content.splitlines()) - 1 for name, content in files.items()}}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ART / "results/session-correspondence")
    parser.add_argument("--write-tables", action="store_true")
    args = parser.parse_args()
    tables, summary = verify(args.results)
    for name, content in tables.items():
        path = args.results / name
        if args.write_tables:
            path.write_bytes(content)
        else:
            require(path.read_bytes() == content, f"derived table differs: {name}")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
