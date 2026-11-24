"""Read-only, complete-history validation of native initial-store evidence."""
from collections import Counter

from .io import fields, integer, read, read_lines, require, same
from . import oracle


from .contract import CONTRACT, METHODS, SOURCE



def validate_inputs(value):
    fields(value, ("contract", "fixture_rows", "candidate_families", "cases"), "input document")
    require(same(value["contract"], CONTRACT), "caller/observation/restoration contract differs")
    require(same(value["fixture_rows"], {str(n): oracle.rows(n, (1 << n) - 1) for n in range(2, 7)}),
            "complete fixture rows differ")
    require(same(value["candidate_families"], {str(n): oracle.family(n) for n in range(2, 7)}),
            "supplied fixed bijection family differs")
    require(type(value["cases"]) is list, "case list required")
    seen = set()
    coverage = set()
    for case in value["cases"]:
        fields(case, ("id", "size", "initial", "observation", "kind", "anchors", "word"), "case")
        integer(case["size"], "case session count", 2, 6)
        integer(case["initial"], "case initial store", 0, (1 << case["size"]) - 1)
        require(type(case["id"]) is str and case["id"] not in seen, "unique case identity required")
        seen.add(case["id"])
        require(type(case["observation"]) is str and case["observation"] in ("projected", "selected-row"),
                "declared observation is invalid")
        require(type(case["kind"]) is str and case["kind"] in ("optimal", "reset-control"), "declared caller kind is invalid")
        require(same(case["anchors"], []), "native study has no supplied anchors")
        require(type(case["word"]) is list, "declared caller word must be a list")
        for operation in case["word"]:
            oracle.validate_operation(operation, case["size"], case["kind"])
        item = (case["size"], case["initial"], case["observation"], case["kind"])
        require(item not in coverage, "duplicate native task")
        coverage.add(item)
        if case["kind"] == "optimal":
            expected_id = f"n{case['size']}-initial{case['initial']}-{case['observation']}"
        else:
            require(case["initial"] == (1 << (case["size"] - 2)) - 1, "reset control must initially omit the final two rows")
            expected_id = f"n{case['size']}-reset-initial-{case['observation']}"
        require(case["id"] == expected_id, "case identity disagrees with its inputs")
    expected = {(n, initial, observation, "optimal") for n in range(2, 7)
                for initial in range(1 << n) for observation in ("projected", "selected-row")}
    expected |= {(n, (1 << (n - 2)) - 1, observation, "reset-control")
                 for n in range(2, 7) for observation in ("projected", "selected-row")}
    require(coverage == expected, "native initial-store/observation coverage differs")


def validate_acquisition(value, reports):
    fields(value, ("status", "source", "methods", "source_admission", "dependencies",
                   "dependency_check_passed", "baseline_source_modified", "native_cases",
                   "production_requests", "fixture_reconstructions", "elapsed_seconds", "python", "platform",
                   "started_utc", "finished_utc", "provenance"), "acquisition receipt")
    require(value["status"] == "ACQUIRED" and value["source"] == SOURCE and same(value["methods"], METHODS),
            "acquisition source identity differs")
    require(value["source_admission"] == "source_study/stateful_sequence/source.py" and
            value["dependencies"] == "source_study/historical_h19/requirements.lock", "acquisition source/dependency gate differs")
    require(value["dependency_check_passed"] is True and value["baseline_source_modified"] is False,
            "acquisition source or native dependency gate failed")
    for key in ("native_cases", "production_requests", "fixture_reconstructions"):
        integer(value[key], "acquisition " + key)
    require(value["native_cases"] == len(reports), "acquisition case count differs")
    require(value["production_requests"] == sum(row["counts"]["requests"] for row in reports),
            "acquisition production request count differs")
    require(value["fixture_reconstructions"] == sum(row["counts"]["restore_complete"] + row["counts"]["reset_initial"] for row in reports),
            "acquisition fixture reconstruction count differs")
    require(type(value["elapsed_seconds"]) in (int, float) and value["elapsed_seconds"] >= 0,
            "acquisition duration must be nonnegative")
    for key in ("python", "platform"):
        require(type(value[key]) is str and bool(value[key]), "acquisition runtime metadata required")


def verify(directory):
    inputs = read(directory / "inputs.json.gz")
    validate_inputs(inputs)
    traces = read_lines(directory / "native-traces.jsonl.gz")
    require(len(traces) == len(inputs["cases"]), "native record coverage differs")
    reports = [oracle.certify(case, trace) for case, trace in zip(inputs["cases"], traces)]
    receipt = read(directory / "acquisition.json")
    validate_acquisition(receipt, reports)
    from .provenance import verify as verify_provenance
    verify_provenance(directory, receipt)
    groups = {}
    for kind in ("optimal", "reset-control"):
        selected = [row for row in reports if row["kind"] == kind]
        counts = Counter()
        for row in selected:
            counts.update(row["counts"])
        groups[kind] = {"cases": len(selected), "initial_store_contexts": len({(row["size"], row["initial"]) for row in selected}),
                        **dict(counts), "fixed_binding_histories": sum(row["tested_bindings"] for row in selected),
                        "request_comparisons": sum(row["request_comparisons"] for row in selected)}
    by_observation = {}
    for observation in ("projected", "selected-row"):
        selected = [row for row in reports if row["kind"] == "optimal" and row["observation"] == observation]
        by_observation[observation] = {"cases": len(selected),
                                      "requests": sum(row["counts"]["requests"] for row in selected),
                                      "restore_complete": sum(row["counts"]["restore_complete"] for row in selected)}
    return {"status": "PASS", "native_execution_scope": "258 complete newly executed words on one selected upstream session interface",
            "history_rule": "One fixed binding per complete history; reconstruction preserves every earlier observation.",
            "comparison_rule": "Every supplied binding is evaluated through every recorded request, including after its first disagreement.",
            "optimal": groups["optimal"], "reset_control": groups["reset-control"],
            "optimal_by_observation": by_observation, "cases": reports}
