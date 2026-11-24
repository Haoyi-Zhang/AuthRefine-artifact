#!/usr/bin/env python3
"""Equal-output family diagnosis on source tables and stateful controlled cases.

The comparison searches share the reference evaluator and replay routine with
the two shared profiles. This isolates traversal and local-support grouping, not
independent semantic oracle or an implementation of CanCheck, SPACE, or FTS tools.
"""
from __future__ import annotations

import argparse
from collections import deque
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from checker import inspect_policy, inspect_machine, reference_step, ensure
from compiler import compile_policy
from extensions import (binding_profile, _normalize_family, _WorkBudget,
                        _reference_replay, DEFAULT_FAMILY_LIMIT)
from family_diagnosis import support_indexed_profile
from language import normalize

MODES = ("shared-target", "per-binding-target", "per-binding-product", "support-indexed")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def output_rows(report):
    return [{key: row[key] for key in ("binding", "equivalent", "length",
                                     "indices", "trace")}
            for row in report["profiles"]]


def search_family(policy, machine, mode, family=None, budget=2_000_000):
    """Complete per-binding BFS, with one schema/family validation per call.

    Each search ends at its first mismatch.  The product retains (reference,
    target) pairs; the target baseline uses the same supplied decoder as the
    shared method.  Both return every binding's actual shortest replay.
    """
    ensure(mode in ("per-binding-target", "per-binding-product"), "comparison mode")
    inspect_policy(policy)
    inspect_machine(policy, machine, compare_initial=False)
    work = _WorkBudget(budget)
    bindings = _normalize_family(policy, family, work, DEFAULT_FAMILY_LIMIT)
    initial = sum(1 << i for i, (_, v) in enumerate(policy["state"]) if v)
    rows = []
    graph_nodes = 0
    graph_edges = 0
    semantic_steps = 0
    for binding in bindings:
        if initial != machine["observations"][machine["initial"]]:
            rows.append(dict(binding=binding, equivalent=False, length=0,
                             indices=[], trace=[]))
            continue
        start = ((initial, machine["initial"]) if mode == "per-binding-product"
                 else machine["initial"])
        queue = deque([(start, [])])
        visited = {start}
        failed = None
        while queue and failed is None:
            node, prefix = queue.popleft()
            graph_nodes += 1
            if mode == "per-binding-product":
                source, target = node
            else:
                target = node
                source = machine["observations"][target]
            for index, request in enumerate(machine["alphabet"]):
                work.charge(category="semantic_steps")
                semantic_steps += 1
                result = reference_step(policy, source, request, binding)
                decision, successor = machine["transitions"][target][index]
                expected = (decision, machine["observations"][successor])
                graph_edges += 1
                if result != expected:
                    indices = prefix + [index]
                    trace = _reference_replay(policy, machine, indices,
                                              [binding] * len(indices), work=work)
                    ensure(trace and not trace[-1]["compared_equal"] and
                           all(r["compared_equal"] for r in trace[:-1]),
                           "comparison replay")
                    failed = dict(binding=binding, equivalent=False,
                                  length=len(indices), indices=indices, trace=trace)
                    break
                following = ((result[1], successor) if mode == "per-binding-product"
                             else successor)
                if following not in visited:
                    visited.add(following)
                    queue.append((following, prefix + [index]))
        rows.append(failed or dict(binding=binding, equivalent=True,
                                   length=None, indices=None, trace=None))
    return {"profiles": rows, "graph_nodes": graph_nodes,
            "graph_edges": graph_edges, "transition_evaluations": semantic_steps,
            **work.report()}


def run_method(case, mode):
    p, m = case["policy"], case["machine"]
    if mode in ("shared-target", "support-indexed"):
        result = (binding_profile if mode == "shared-target" else support_indexed_profile)(p, m, family=case.get("family"))
        result["graph_nodes"] = result["target_reachable_states"]
        result["graph_edges"] = result["work_breakdown"].get("graph_edges", 0)
    else:
        result = search_family(p, m, mode, family=case.get("family"))
    return result


def staged_policy(bits, aliases, regime):
    """Control state depth and family size without changing output requirements.

    A tick advances a saturating binary counter.  Probes preserve state.  Before
    the final counter value every probe allows; there a role binding matters.
    The all-match arm assigns both roles, the late-failure arm only one role.
    The early-failure arm changes an initial target probe to deny.  These are
    constructed controls, not additional applications or naturally sampled bugs.
    """
    ensure(bits in (1, 3, 5) and aliases in (1, 4, 8), "control shape")
    ensure(regime in ("all-match", "late-failure", "early-failure"), "control regime")
    names = [f"b{i}" for i in range(bits)]
    probes = [f"probe-{i:02d}" for i in range(aliases)]
    p = {"principals": ["u"], "resources": ["o"],
         "actions": probes + ["tick"], "roles": ["r", "s"],
         "members": [["u", "r"]] + ([["u", "s"]] if regime == "all-match" else []),
         "state": [[b, False] for b in names],
         "aliases": [{"name": f"role-{i:02d}", "kind": "role", "candidates": ["r", "s"]}
                     for i in range(aliases)], "rules": []}
    action = lambda a: {"field": "action", "name": a, "negated": False}
    bit = lambda b, v: {"field": "state", "name": b, "value": v}
    for i, name in enumerate(probes):
        p["rules"].append({"decision": "deny", "guard": [action(name)] +
                           [bit(b, True) for b in names] +
                           [{"field": "role", "alias": f"role-{i:02d}", "negated": True}],
                           "updates": []})
        p["rules"].append({"decision": "allow", "guard": [action(name)], "updates": []})
    for i, name in enumerate(names):
        p["rules"].append({"decision": "allow", "guard": [action("tick")] +
                           [bit(b, True) for b in names[:i]] + [bit(name, False)],
                           "updates": [{"name": b, "value": False} for b in names[:i]] +
                           [{"name": name, "value": True}]})
    p["rules"].append({"decision": "allow", "guard": [action("tick")], "updates": []})
    p = normalize(p)
    m = compile_policy(p, {a["name"]: "r" for a in p["aliases"]})
    if regime == "early-failure":
        m["transitions"][m["initial"]][0] = ["deny", m["initial"]]
    return {"id": f"control-s{1 << bits}-f{1 << aliases}-{regime}",
            "group": "controlled", "state_count": 1 << bits,
            "family_size": 1 << aliases, "regime": regime,
            "policy": p, "machine": m,
            "expected_matching": (1 << aliases) if regime == "all-match" else
                                 (1 if regime == "late-failure" else 0),
            "expected_failure_length": None if regime == "all-match" else
                                       ((1 << bits) if regime == "late-failure" else 1)}


def dense_policy(bits, aliases):
    """Every cell depends syntactically on all aliases: no group reduction.

    Both candidate roles are held, so all interpretations agree.  The syntactic
    support approximation deliberately cannot exploit that semantic equality.
    """
    base = staged_policy(bits, aliases, "all-match")
    p = deepcopy(base["policy"])
    p["actions"] = ["tick"]
    p["rules"] = [r for r in p["rules"]
                  if any(a.get("field") == "action" and a.get("name") == "tick"
                         for a in r["guard"])]
    for rule in p["rules"]:
        rule["guard"].extend({"field": "role", "alias": a["name"], "negated": False}
                             for a in p["aliases"])
    p = normalize(p)
    return {"id": f"dense-s{1 << bits}-f{1 << aliases}", "group": "controlled",
            "state_count": 1 << bits, "family_size": 1 << aliases,
            "regime": "dense-support", "policy": p, "machine": compile_policy(p),
            "expected_matching": 1 << aliases, "expected_failure_length": None}


def cases():
    result = [staged_policy(b, a, r) for b in (1, 3, 5) for a in (1, 4, 8)
              for r in ("all-match", "late-failure", "early-failure")]
    result.extend(dense_policy(b, a) for b in (1, 3) for a in (1, 4, 8))
    singleton = staged_policy(5, 8, "late-failure")
    singleton["id"] = "singleton-s32-f1"
    singleton["regime"] = "singleton"
    singleton["family_size"] = 1
    for alias in singleton["policy"]["aliases"]:
        alias["candidates"] = ["r"]
    singleton["policy"] = normalize(singleton["policy"])
    singleton["expected_matching"] = 1
    singleton["expected_failure_length"] = None
    result.append(singleton)
    previous = ROOT / "results/source-observer/comparisons.json"
    for row in json.loads(previous.read_text())["stateful_diagnosis"]:
        result.append({"id": "healthchecks-resume-" + row["form"],
                       "group": "source-derived", "regime": "observed",
                       "policy": row["policy"], "machine": row["model"],
                       "provenance": str(previous.relative_to(ROOT)),
                       "expected_matching": 1, "expected_failure_length": 1})
    session = ROOT / "results/native-session"
    diagnosis = json.loads((session / "diagnosis.json").read_text())
    acquired = json.loads((session / "native-observations.json").read_text())
    for name, matched, length in (("baseline", 1, 2), ("omit_delete", 0, 1)):
        result.append({"id": "piccolo-session-" + name,
                       "group": "source-derived" if name == "baseline" else "source-derived-control",
                       "regime": "observed" if name == "baseline" else "introduced-control",
                       "policy": diagnosis["policy"], "machine": acquired[name]["machine"],
                       "family": diagnosis["supplied_family"],
                       "provenance": str(session.relative_to(ROOT)),
                       "expected_matching": matched, "expected_failure_length": length})
    return result


def child(args):
    payload = json.loads(sys.stdin.buffer.read())
    records = []
    for case in payload:
        before, cpu = time.perf_counter_ns(), time.process_time_ns()
        result = run_method(case, args.child)
        diagnosis_ns = time.perf_counter_ns() - before
        cpu_ns = time.process_time_ns() - cpu
        begin = time.perf_counter_ns()
        output = encoded(output_rows(result))
        serialization_ns = time.perf_counter_ns() - begin
        matched = sum(r["equivalent"] for r in result["profiles"])
        lengths = sorted({r["length"] for r in result["profiles"] if not r["equivalent"]})
        ensure(matched == case["expected_matching"], "control matching family")
        ensure(lengths == ([] if case["expected_failure_length"] is None else
                           [case["expected_failure_length"]]), "control first failure")
        records.append({"id": case["id"], "diagnosis_wall_ns": diagnosis_ns,
                        "diagnosis_cpu_ns": cpu_ns, "serialization_ns": serialization_ns,
                        "output_sha256": hashlib.sha256(output).hexdigest(),
                        "output_bytes": len(output), "bindings": len(result["profiles"]),
                        "matching": matched, "failure_lengths": lengths,
                        "semantic_steps": result["transition_evaluations"],
                        "graph_nodes": result["graph_nodes"],
                        "graph_edges": result["graph_edges"],
                        "replay_steps": result["work_breakdown"].get("replay_steps", 0),
                        "support_queries": result.get("support_queries", 0),
                        "family_projection_evaluations": result.get("family_projection_evaluations", 0),
                        "family_projection_coordinates": result.get("family_projection_coordinates", 0),
                        "index_memberships_created": result.get("index_memberships_created", 0),
                        "index_memberships_removed": result.get("index_memberships_removed", 0),
                        "peak_cached_memberships": result.get("peak_cached_memberships", 0)})
    print(json.dumps({"mode": args.child, "records": records,
                      "python": sys.version, "platform": platform.platform()}))


def run(output, repeats):
    ensure(not output.exists(), "fresh benchmark destination required")
    ensure(3 <= repeats <= 15, "repeats in 3..15")
    output.mkdir(parents=True)
    before = time.perf_counter_ns()
    cohort = cases()
    setup_ns = time.perf_counter_ns() - before
    data = encoded(cohort)
    (output / "inputs.json").write_bytes(data)
    # Retain the actual replay-bearing outputs once.  Every timed run must hash
    # to this same representation; different tie-breaking is not silently ignored.
    canonical = []
    for case in cohort:
        values = [output_rows(run_method(case, mode)) for mode in MODES]
        ensure(all(v == values[0] for v in values), "full family/witness/replay equality")
        canonical.append({"id": case["id"], "profiles": values[0],
                          "sha256": digest(values[0])})
    (output / "profiles.json").write_bytes(encoded(canonical))
    expected = {r["id"]: r["sha256"] for r in canonical}
    trials = []
    # Rotated process order; one process per method per repeat.  Per-case clocks
    # exclude common process startup/input decoding and include input validation,
    # family construction, graph work, semantic checks, and every witness replay.
    for repeat in range(repeats):
        for mode in MODES[repeat % len(MODES):] + MODES[:repeat % len(MODES)]:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", mode]
            begin = time.perf_counter_ns()
            proc = subprocess.run(command, input=data, capture_output=True, timeout=180,
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            process_ns = time.perf_counter_ns() - begin
            stem = f"trial-{repeat:02d}-{mode}"
            (output / (stem + ".stdout.json")).write_bytes(proc.stdout)
            (output / (stem + ".stderr.log")).write_bytes(proc.stderr)
            ensure(proc.returncode == 0, "benchmark child failed")
            trial = json.loads(proc.stdout)
            ensure(len(trial["records"]) == len(cohort), "benchmark record count")
            ensure(all(r["output_sha256"] == expected[r["id"]] for r in trial["records"]),
                   "timed semantic output changed")
            trial.update(repeat=repeat, process_wall_ns=process_ns, exit_code=proc.returncode)
            trials.append(trial)
        print(f"completed rotated repeat {repeat + 1}/{repeats}", flush=True)
    summary = []
    deterministic = ("output_sha256", "output_bytes", "bindings", "matching", "failure_lengths",
                     "semantic_steps", "graph_nodes", "graph_edges", "replay_steps", "support_queries",
                     "family_projection_evaluations", "family_projection_coordinates",
                     "index_memberships_created", "index_memberships_removed", "peak_cached_memberships")
    for case in cohort:
        row = {"id": case["id"], "group": case["group"], "regime": case["regime"], "methods": {}}
        for mode in MODES:
            values = [next(r for r in t["records"] if r["id"] == case["id"])
                      for t in trials if t["mode"] == mode]
            for field in deterministic:
                ensure(all(v[field] == values[0][field] for v in values),
                       "nondeterministic benchmark count")
            metrics = {field: values[0][field] for field in deterministic}
            for field in ("diagnosis_wall_ns", "diagnosis_cpu_ns", "serialization_ns"):
                sample = [v[field] for v in values]
                metrics[field] = {"median": statistics.median(sample), "min": min(sample),
                                  "max": max(sample), "samples": sample}
            row["methods"][mode] = metrics
        summary.append(row)
    report = {"status": "PASS", "cases": len(cohort), "controlled_cases": 34,
              "source_derived_tables": 3, "source_derived_control_tables": 1,
              "independent_source_applications_added": 0,
              "repeats": repeats, "methods": list(MODES), "records": summary,
              "construction_wall_ns": setup_ns, "input_sha256": hashlib.sha256(data).hexdigest(),
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [Path(__file__).resolve()] +
                                [ROOT / "src" / n for n in ("checker.py", "extensions.py", "compiler.py", "language.py", "family_diagnosis.py")]},
              "scope": ["Complete matching family, exact shortest words and all replay rows are identical.",
                        "All methods use the same reference evaluator; this isolates traversal, not semantic correctness.",
                        "Per-binding target BFS is supplied the same complete state decoder as the shared method.",
                        "Cases deliberately vary matching fraction and failure depth; these are no prevalence sample.",
                        "Timing includes schema validation, family enumeration, graph operations, checks and replay.",
                        "Setup records control construction and loading of retained source-derived tables; source acquisition is not retimed.",
                        "Process startup/input decoding are outside per-case clocks; complete child time and output encoding are separate.",
                        "Sequential rotated single-host runs; ranges are observed ranges, not confidence intervals.",
                        "No unused alias declarations or target-only phase padding are added to these controls.",
                        "In all-match controls both candidate roles are held: distinct interpretations intentionally agree.",
                        "Support indexing retains its construction, retirement, and full per-binding replay cost."]}
    (output / "trials.json").write_bytes(encoded(trials))
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(cohort), "repeats": repeats}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--repeats", type=int, default=7)
    ap.add_argument("--child", choices=MODES)
    args = ap.parse_args()
    if args.child:
        child(args)
    else:
        if args.output is None:
            ap.error("--output is required")
        run(args.output, args.repeats)
