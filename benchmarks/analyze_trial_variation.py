#!/usr/bin/env python3
"""Reconcile complete-profile trials and describe their observed variation.

This reads an existing campaign. It neither reruns diagnosis nor estimates
population confidence intervals. Every ratio envelope uses the most adverse
observed numerator and denominator, across the seven retained processes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values: list[int]) -> dict:
    if len(values) != 7 or any(type(v) is not int or v <= 0 for v in values):
        raise ValueError("Expected seven positive integer nanosecond observations")
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {"samples_ns": values, "median_ns": statistics.median(values),
            "q1_ns": quartiles[0], "q3_ns": quartiles[2],
            "minimum_ns": min(values), "maximum_ns": max(values)}


def run(results: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    paths = {name: results / name for name in ("trials.json", "summary.json")}
    trials = json.loads(paths["trials.json"].read_text())
    summary = json.loads(paths["summary.json"].read_text())
    methods = summary["methods"]
    if summary["repeats"] != 7 or len(trials) != 7 * len(methods):
        raise ValueError("Unexpected campaign shape")
    expected_cases = [row["id"] for row in summary["records"]]
    samples = {}
    seen = set()
    environments = set()
    for trial in trials:
        identity = trial["mode"], trial["repeat"]
        if identity in seen or identity[0] not in methods or identity[1] not in range(7):
            raise ValueError("Duplicate or unexpected process trial")
        seen.add(identity)
        if trial["exit_code"] != 0:
            raise ValueError("A process trial failed")
        environments.add((trial["python"], trial["platform"]))
        if [r["id"] for r in trial["records"]] != expected_cases:
            raise ValueError("Trial case order differs from the campaign")
        for record in trial["records"]:
            samples[(record["id"], *identity)] = record
    rows = []
    for case in summary["records"]:
        measurements = {}
        output_hashes = set()
        for method in methods:
            raw = [samples[(case["id"], method, i)] for i in range(7)]
            declared = case["methods"][method]
            for record in raw:
                if record["output_sha256"] != declared["output_sha256"]:
                    raise ValueError("Output identity differs from its summary")
                if record["output_bytes"] != declared["output_bytes"]:
                    raise ValueError("Output size differs from its summary")
                output_hashes.add(record["output_sha256"])
            metrics = {}
            for metric in ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns"):
                values = [r[metric] for r in raw]
                original = declared[metric]
                if (values != original["samples"] or
                        statistics.median(values) != original["median"] or
                        min(values) != original["min"] or max(values) != original["max"]):
                    raise ValueError("Raw timing observations disagree with their summary")
                metrics[metric] = describe(values)
            measurements[method] = metrics
        if len(output_hashes) != 1:
            raise ValueError("Methods did not produce identical complete outputs")
        product = measurements["per-binding-product"]["diagnosis_wall_ns"]
        indexed = measurements["support-indexed"]["diagnosis_wall_ns"]
        ratio = product["median_ns"] / indexed["median_ns"]
        low = product["minimum_ns"] / indexed["maximum_ns"]
        high = product["maximum_ns"] / indexed["minimum_ns"]
        if not low <= ratio <= high:
            raise ValueError("Median ratio is outside the observed envelope")
        rows.append({"id": case["id"], "group": case["group"],
                     "regime": case["regime"], "methods": measurements,
                     "product_over_indexed": {"median_ratio": ratio,
                         "observed_envelope_lower": low,
                         "observed_envelope_upper": high,
                         "relation_to_one": "above" if low > 1 else
                                            "below" if high < 1 else "crosses"}})
    report = {"status": "PASS", "cases": len(rows), "methods": methods,
              "processes": len(trials), "timed_case_records": len(samples),
              "metric_summaries_reconciled": len(rows) * len(methods) * 3,
              "repeats_per_method": 7, "quartiles": "inclusive linear interpolation",
              "ratio_envelope": "min(product)/max(indexed), max(product)/min(indexed)",
              "scope": "Descriptive variation of retained process trials on one host; no confidence or prevalence inference.",
              "environments": [{"python": p, "platform": s} for p, s in sorted(environments)],
              "input_sha256": {name: digest(path) for name, path in paths.items()},
              "script_sha256": digest(Path(__file__)), "records": rows}
    output.mkdir(parents=True)
    (output / "variation.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "timing-summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case", "method", "metric", "n", "median_ns", "q1_ns",
                         "q3_ns", "minimum_ns", "maximum_ns"])
        for row in rows:
            for method, metrics in row["methods"].items():
                for metric, values in metrics.items():
                    writer.writerow([row["id"], method, metric, 7, values["median_ns"],
                                     values["q1_ns"], values["q3_ns"],
                                     values["minimum_ns"], values["maximum_ns"]])
    return {key: report[key] for key in ("status", "cases", "processes",
                                        "timed_case_records", "metric_summaries_reconciled")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.results, arguments.output)))
