#!/usr/bin/env python3
"""Independent diagnosis audit for correlated families and overlapping supports.

The finite domain is one four-state/four-request reference contract, all 255
nonempty subfamilies of its eight three-alias bindings, and all 65 baseline or
single-cell-perturbed targets. The source oracle is a direct table definition;
it does not call production policy evaluation, support discovery, or BFS.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from copy import deepcopy
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import family_diagnosis as implementation

ACTIONS = ("ab", "bc", "ca", "tick")
ALIASES = ("x", "y", "z")
PAIRS = {"ab": ("x", "y"), "bc": ("y", "z"), "ca": ("z", "x")}
THRESHOLDS = {"ab": 1, "bc": 2, "ca": 3}
BINDINGS = [dict(zip(ALIASES, values)) for values in product(("r", "s"), repeat=3)]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_cell(state, action, binding):
    """Separate tabular specification, not a policy AST interpreter."""
    if action == "tick":
        return "allow", min(state + 1, 3)
    allowed = state < THRESHOLDS[action] or all(binding[name] == "r" for name in PAIRS[action])
    return ("allow" if allowed else "deny"), state


def policy():
    """Encode the declared table with deliberately recurring syntactic supports.

    At phase zero every probe allows, although alias guards are inspected.
    The same support projections later yield differing decisions. Thus a cache
    of earlier *verdicts*, rather than memberships, is detectably unsound.
    """
    result = {"principals": ["u"], "resources": ["o"], "actions": list(ACTIONS),
              "roles": ["r", "s"], "members": [["u", "r"]],
              "state": [["b0", False], ["b1", False]],
              "aliases": [{"name": name, "kind": "role", "candidates": ["r", "s"]}
                          for name in ALIASES], "rules": []}
    def phase_guard(phase, action):
        return [{"field": "action", "name": action, "negated": False},
                {"field": "state", "name": "b0", "value": bool(phase & 1)},
                {"field": "state", "name": "b1", "value": bool(phase & 2)}]
    for phase in range(4):
        for action in ACTIONS[:3]:
            for alias in PAIRS[action]:
                result["rules"].append({
                    "decision": "deny" if phase >= THRESHOLDS[action] else "allow",
                    "guard": phase_guard(phase, action) +
                             [{"field": "role", "alias": alias, "negated": True}],
                    "updates": [],
                })
        next_phase = min(phase + 1, 3)
        result["rules"].append({"decision": "allow", "guard": phase_guard(phase, "tick"),
                               "updates": [{"name": "b0", "value": bool(next_phase & 1)},
                                           {"name": "b1", "value": bool(next_phase & 2)}]})
    result["rules"].append({"decision": "allow", "guard": [], "updates": []})
    return result


def baseline_target():
    return {"state_names": ["b0", "b1"],
            "alphabet": [["u", "o", action] for action in ACTIONS],
            "observations": list(range(4)), "initial": 0,
            "transitions": [[list(source_cell(state, action, BINDINGS[0])) for action in ACTIONS]
                            for state in range(4)]}


def targets():
    original = baseline_target()
    yield {"id": "baseline", "perturbation": None, "machine": original}
    for state in range(4):
        for request in range(4):
            decision, successor = original["transitions"][state][request]
            changed = deepcopy(original)
            changed["transitions"][state][request][0] = "deny" if decision == "allow" else "allow"
            yield {"id": f"decision-{state}-{request}",
                   "perturbation": {"state": state, "request": request, "field": "decision"},
                   "machine": changed}
            for other in range(4):
                if other == successor:
                    continue
                changed = deepcopy(original)
                changed["transitions"][state][request][1] = other
                yield {"id": f"successor-{state}-{request}-{other}",
                       "perturbation": {"state": state, "request": request, "field": "successor", "value": other},
                       "machine": changed}


def family(mask):
    return [dict(binding) for index, binding in enumerate(BINDINGS) if mask & (1 << index)]


def oracle_profile(machine, binding):
    """Explicit product BFS using only source_cell and the supplied target table."""
    initial = machine["initial"]
    if machine["observations"][initial] != 0:
        return {"binding": binding, "equivalent": False, "length": 0,
                "indices": [], "trace": [], "reason": "initial observation"}
    waiting = deque([(0, initial, [])])
    seen = {(0, initial)}
    selected = None
    while waiting and selected is None:
        source, target, prefix = waiting.popleft()
        for index, action in enumerate(ACTIONS):
            observed_decision, following = machine["transitions"][target][index]
            actual = source_cell(source, action, binding)
            expected = observed_decision, machine["observations"][following]
            if actual != expected:
                selected = prefix + [index]
                break
            node = (actual[1], following)
            if node not in seen:
                seen.add(node)
                waiting.append((*node, prefix + [index]))
    if selected is None:
        return {"binding": binding, "equivalent": True, "length": None, "indices": None, "trace": None}
    source, target, trace = 0, initial, []
    last_target = last_request = None
    for index in selected:
        decision, following = machine["transitions"][target][index]
        actual = source_cell(source, ACTIONS[index], binding)
        expected = decision, machine["observations"][following]
        trace.append({"request": machine["alphabet"][index], "binding": binding,
                      "source": list(actual), "target": list(expected),
                      "decision_equal": actual[0] == expected[0],
                      "state_equal": actual[1] == expected[1], "compared_equal": actual == expected})
        last_target, last_request = target, index
        source, target = actual[1], following
    return {"binding": binding, "equivalent": False, "length": len(selected),
            "indices": selected, "trace": trace, "target_state": last_target, "request": last_request}


def expected_family(machine, mask):
    return [oracle_profile(machine, binding) for binding in family(mask)]


def check_report(report, expected):
    if report["profiles"] != expected:
        raise AssertionError("complete profile or fixed-binding replay differs from direct tables")
    matched = sum(row["equivalent"] for row in expected)
    finite = [row["length"] for row in expected if not row["equivalent"]]
    aggregate = {"bindings": len(expected), "matching_bindings": matched,
                 "failing_bindings": len(expected) - matched,
                 "classification": "all" if matched == len(expected) else "none" if matched == 0 else "some",
                 "shortest_failure": min(finite) if finite else None,
                 "strata": dict(Counter("infinity" if row["equivalent"] else str(row["length"]) for row in expected))}
    if any(report[key] != value for key, value in aggregate.items()):
        raise AssertionError("profile aggregates differ from the independent complete family")
    return aggregate


def mutation_controls():
    p, m = policy(), baseline_target()
    outcomes = []
    original_step = implementation.reference_step
    original_support = implementation.support
    original_normalize = implementation._normalize_family
    def run_control(name, patches, mask=255):
        result = None
        expected = expected_family(m, mask)
        try:
            with patches:
                result = implementation.support_indexed_profile(p, m, family(mask))
                check_report(result, expected)
        except (AssertionError, ValueError) as error:
            outcomes.append({"name": name, "detected": True, "reason": str(error),
                             "detection_stage": "independent-comparison" if result is not None else "implementation-invariant",
                             "expected_bindings": len(expected),
                             "actual_bindings": result["bindings"] if result is not None else None,
                             "expected_matching": sum(row["equivalent"] for row in expected),
                             "actual_matching": result["matching_bindings"] if result is not None else None})
        else:
            raise AssertionError("audit did not reject mutation: " + name)
    # Unsound optimization: re-use a prior decision for a support projection
    # in a later state. Probe post-states stutter, so this masks delayed failures.
    decisions = {}
    def stale_decision(p, state, request, binding):
        if request[2] == "tick":
            return original_step(p, state, request, binding)
        key = (request[2], tuple((name, binding[name]) for name in original_support(p, state, request)))
        decisions.setdefault(key, original_step(p, state, request, binding)[0])
        return decisions[key], state
    run_control("reuse-earlier-support-projection-decision",
                patch.object(implementation, "reference_step", stale_decision))
    run_control("omit-overlapping-support-coordinate",
                patch.object(implementation, "support", lambda p, s, r: [x for x in original_support(p, s, r) if x != "y"]))
    run_control("cartesian-complete-an-explicit-correlated-family",
                patch.object(implementation, "_normalize_family", lambda p, f, w, n: original_normalize(p, None, w, n)), mask=129)
    return outcomes


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    p, machines = policy(), list(targets())
    if len(machines) != 65 or len({encoded(t["machine"]) for t in machines}) != 65:
        raise AssertionError("target perturbation domain is incomplete or duplicated")
    inputs = {"policy": p, "all_bindings": BINDINGS, "targets": machines,
              "family_masks": list(range(1, 256)), "source_tables": [
                  {"binding": b, "transitions": [[list(source_cell(q, a, b)) for a in ACTIONS] for q in range(4)]}
                  for b in BINDINGS]}
    (output / "inputs.json").write_bytes(encoded(inputs))
    counts, strata, cardinalities = Counter(), Counter(), Counter()
    digest = hashlib.sha256()
    total_profiles = total_replay = 0
    with (output / "profiles.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
            for target_number, target in enumerate(machines, start=1):
                m = target["machine"]
                # A fixed binding's independent answer does not depend on which
                # other members the explicit family contains. Reuse that answer,
                # never an implementation verdict, across the 255 subfamilies.
                direct = [oracle_profile(m, b) for b in BINDINGS]
                for mask in range(1, 256):
                    selected = [row for i, row in enumerate(direct) if mask & (1 << i)]
                    report = implementation.support_indexed_profile(p, m, family(mask))
                    aggregate = check_report(report, selected)
                    row = {"target": target["id"], "family_mask": mask, **report}
                    data = encoded(row) + b"\n"
                    stream.write(data); digest.update(data)
                    counts[aggregate["classification"]] += 1
                    strata.update(aggregate["strata"])
                    cardinalities[len(selected)] += 1
                    total_profiles += len(selected)
                    total_replay += sum(len(r["trace"] or []) for r in selected)
                if target_number % 13 == 0:
                    print(f"checked {target_number}/65 target tables", flush=True)
    base = implementation.support_indexed_profile(p, baseline_target())
    if base["cached_supports"] != 4 or base["index_memberships_created"] != 32 or base["index_memberships_removed"] != 28:
        raise AssertionError("baseline no longer exercises all four cached indexes before retirement")
    controls = mutation_controls()
    sources = [Path(__file__), ROOT / "src/family_diagnosis.py", ROOT / "src/checker.py", ROOT / "src/extensions.py"]
    summary = {"status": "PASS", "family_diagnoses": sum(counts.values()),
               "target_tables": len(machines), "explicit_families_per_target": 255,
               "binding_profiles_checked": total_profiles, "witness_replay_rows_checked": total_replay,
               "family_classifications": dict(sorted(counts.items())),
               "binding_shortest_lengths": dict(sorted(strata.items())),
               "families_by_cardinality": dict(sorted(cardinalities.items())),
               "baseline": {key: base[key] for key in ("classification", "strata", "cached_supports", "index_memberships_created", "index_memberships_removed", "peak_cached_memberships", "transition_evaluations", "replay_evaluations")},
               "mutation_controls": controls,
               "profiles_uncompressed_sha256": digest.hexdigest(),
               "inputs_sha256": hashlib.sha256(encoded(inputs)).hexdigest(),
               "source_sha256": {str(f.resolve().relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
               "scope": ["One constructed four-state/four-request contract with three binary aliases and recurring pairwise-overlapping supports.",
                         "Every nonempty subset of the eight joint bindings, independently crossed with the 65 baseline/single-cell-perturbed target tables.",
                         "The oracle uses direct source tables and an explicit source/target product, without production stepping, support discovery, family normalization, or target traversal.",
                         "Complete semantic profiles, deterministic shortest words, all replay fields, and family aggregates are compared.",
                         "This is a bounded verification domain, not additional applications, sampled vulnerabilities, or a performance benchmark."]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    (output / "runtime.json").write_text(json.dumps({"wall_seconds": time.perf_counter()-started, "python": sys.version}, indent=2)+"\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
