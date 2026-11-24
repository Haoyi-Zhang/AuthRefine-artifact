#!/usr/bin/env python3
"""Plot all complete-output tasks against the support-indexed algorithm.

The shared loader verifies every plotted summary against the retained worker
records. Ratios compare elapsed times, not unlike backend operation counters.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from reportlab.pdfgen.canvas import Canvas
from figure_typography import WIDTH, INK, ACCENT, SECONDARY, GRID, GUIDE, LIGHT, register_fonts
from draw_evaluation import text, line, rect

ART = Path(__file__).resolve().parents[1]
METHODS = ("per-binding-product", "per-binding-target", "scan", "support-indexed",
           "finite-domain", "cudd")
COHORTS = (("family-cost", "State/support cohort", 38),
           ("session-correspondence", "Session correspondences", 40),
           ("native-policy-store", "Native policy store", 80))
SERIES = (("scan", "Scan", SECONDARY, (1.2, 2.0)),
          ("finite-domain", "Finite-domain", ACCENT, ()),
          ("cudd", "CUDD", INK, (5.0, 2.5)))


def load_checked(results):
    """Check complete task/method denominators and all seven timing samples."""
    report = json.loads((results / "summary.json").read_text())
    trials = json.loads((results / "trials.json").read_text())
    expected_cohorts = {name: count for name, _, count in COHORTS}
    if (report["status"] != "PASS" or report["repeats"] != 7
            or report["methods"] != list(METHODS)
            or report["cohort_tasks"] != expected_cohorts
            or (report["tasks"], report["case_method_pairs"], report["processes"],
                report["timed_task_records"]) != (158, 760, 42, 5320)):
        raise ValueError("Unexpected complete-output comparison denominator")
    rows = {row["id"]: row for row in report["records"]}
    if len(rows) != 158 or Counter(row["cohort"] for row in rows.values()) != expected_cohorts:
        raise ValueError("Missing, duplicate or misclassified comparison task")
    indexed = {}
    for trial in trials:
        identity = trial["repeat"], trial["method"]
        if (identity in indexed or trial["repeat"] not in range(7)
                or trial["method"] not in METHODS or trial["exit_code"] != 0
                or trial["complete_outputs_compared"] is not True):
            raise ValueError("Invalid comparison worker")
        raw = json.loads((results / trial["stdout"]).read_text())
        if any(trial.get(key) != value for key, value in raw.items()):
            raise ValueError("Aggregate worker differs from raw stdout")
        if (results / trial["stderr"]).read_text():
            raise ValueError("Comparison worker has nonempty stderr")
        selected = [row["id"] for row in rows.values() if trial["method"] in row["methods"]]
        if [row["id"] for row in trial["records"]] != selected:
            raise ValueError("Worker task order or denominator differs")
        indexed[identity] = {row["id"]: row for row in trial["records"]}
    if set(indexed) != {(r, m) for r in range(7) for m in METHODS}:
        raise ValueError("The seven-run method matrix is incomplete")
    for case, row in rows.items():
        methods = METHODS if row["caller"] == "total" else METHODS[2:]
        if set(row["methods"]) != set(methods):
            raise ValueError("Missing algorithm for the task's output contract")
        if len({m["output_sha256"] for m in row["methods"].values()}) != 1:
            raise ValueError("Algorithms returned different complete profiles")
        for method, summary in row["methods"].items():
            observed = [indexed[r, method][case] for r in range(7)]
            for metric in ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns"):
                samples = [entry[metric] for entry in observed]
                if any(type(value) is not int or value < 0 for value in samples):
                    raise ValueError("Invalid timing sample")
                expected = dict(samples=samples, median=median(samples),
                                min=min(samples), max=max(samples))
                if summary[metric] != expected:
                    raise ValueError("Timing summary differs from raw worker measurements")
            for field in ("output_sha256", "output_bytes", "bindings", "matching",
                          "failure_lengths", "diagnostic_reference_calls", "replay_steps"):
                if any(entry[field] != summary[field] for entry in observed):
                    raise ValueError("Scientific work or output differs across raw workers")
    return report, rows


def draw(results, output):
    report, rows = load_checked(results)
    ratios = {
        (cohort, method): sorted(
            (row["methods"][method]["diagnosis_wall_ns"]["median"]
             / row["methods"]["support-indexed"]["diagnosis_wall_ns"]["median"], row["id"])
            for row in rows.values() if row["cohort"] == cohort)
        for cohort, _, _ in COHORTS for method, _, _, _ in SERIES
    }
    values = [value for sequence in ratios.values() for value, _ in sequence]
    if min(values) <= 0:
        raise ValueError("A timing ratio is not positive")
    lower = min(math.floor(math.log10(min(values))), 0)
    upper = max(math.ceil(math.log10(max(values))), 0)
    if lower == upper:
        upper += 1
    output.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(output / "symbolic-comparison.pdf"), pagesize=(WIDTH, 438),
               invariant=True, initialFontName="Body")
    c.setTitle("Complete diagnostic cost distributions by task cohort")
    c.setCreator(""); c.chart_height = 438; c.chart_labels = []
    left, right = 56, 382
    x = lambda value: left + (math.log10(value) - lower) / (upper - lower) * (right - left)
    for position, (_, label, color, dash) in zip((57, 161, 296), SERIES):
        c.setDash(*dash) if dash else c.setDash()
        line(c, position, 422, position + 22, 422, color, 1.3)
        c.setDash()
        text(c, position + 28, 418.5, label, "left", size=10.5)
    text(c,(left+x(1))/2,400,"Compared faster",size=10)
    text(c,(x(1)+right)/2,400,"Support-indexed faster",size=10)
    plotted = []
    for panel, ((cohort, title, count), bottom) in enumerate(zip(COHORTS, (281, 157, 33))):
        top = bottom + 83
        y = lambda fraction: bottom + 83 * fraction
        text(c, (left + right) / 2, top + 20,
             f"({chr(97 + panel)}) {title} ({count} tasks)", font="Bold", size=11)
        rect(c,left,bottom,x(1)-left,top-bottom,LIGHT)
        for tick in (0, 50, 100):
            yy = y(tick / 100)
            line(c, left, yy, right, yy, GRID, .6)
            text(c, left - 7, yy - 3.3, str(tick), "right", size=10)
        for exponent in range(lower, upper + 1):
            xx = x(10 ** exponent)
            line(c, xx, bottom, xx, top, GRID, .6)
            if panel == 2:
                align = "left" if exponent == lower else ("right" if exponent == upper else "center")
                text(c, xx, bottom - 15, f"{10 ** exponent:g}", align, size=9.0)
        line(c, left, bottom, right, bottom, INK, .6)
        line(c, left, bottom, left, top, INK, .6)
        c.setDash(2, 2)
        line(c, x(1), bottom, x(1), top, GUIDE, .9)
        c.setDash()
        for method, label, color, dash in SERIES:
            samples = ratios[cohort, method]
            if len(samples) != count:
                raise ValueError("Cumulative distribution lost tasks")
            sample_values = [value for value, _ in samples]
            path = c.beginPath()
            path.moveTo(left, bottom)
            for index, (value, _) in enumerate(samples, 1):
                path.lineTo(x(value), y((index - 1) / count))
                path.lineTo(x(value), y(index / count))
            path.lineTo(right, top)
            c.setStrokeColor(color); c.setLineWidth(1.3)
            c.setDash(*dash) if dash else c.setDash()
            c.drawPath(path, stroke=1, fill=0)
            c.setDash()
            plotted.append({"cohort": cohort, "method": method, "tasks": count,
                            "tasks_faster_than_indexed": sum(v < 1 for v, _ in samples),
                            "samples": [{"id": key, "ratio_of_medians": value,
                                         "fraction_at_or_below": bisect_right(sample_values, value) / count}
                                        for value, key in samples]})
    c.saveState(); c.translate(13, 198); c.rotate(90)
    c.setFont("Body", 10.5); c.setFillColor(INK)
    c.drawCentredString(0, 0, "Tasks at or below ratio (%)")
    c.restoreState()
    text(c, (left + right) / 2, 5, "Diagnosis time / support-indexed time (log)", size=10.5)
    c.showPage(); c.save()
    result = {
        "input_summary_sha256": hashlib.sha256((results / "summary.json").read_bytes()).hexdigest(),
        "input_trials_sha256": hashlib.sha256((results / "trials.json").read_bytes()).hexdigest(),
        "raw_timing_samples_verified": True,
        "tasks": report["tasks"], "cohort_tasks": report["cohort_tasks"],
        "ratio_definition": "median(method diagnosis wall time) / median(support-indexed diagnosis wall time) for the same complete-output task",
        "distribution_definition": "Empirical cumulative fraction within each declared task cohort; tasks and callers are not independent applications.",
        "uncertainty": "Each ratio uses seven observed runs. The curve is a distribution over tasks, not a confidence interval or a population estimate.",
        "axes": {"lower": 10 ** lower, "upper": 10 ** upper},
        "series": plotted,
    }
    (output / "symbolic-comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ART / "results/symbolic-comparison")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); register_fonts()
    result = draw(args.results, args.output)
    print(json.dumps({"status": "PASS", "tasks": result["tasks"], "series": len(result["series"])}))
