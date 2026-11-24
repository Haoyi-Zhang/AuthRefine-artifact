#!/usr/bin/env python3
"""Independent checks of support grouping under partial caller protocols.

The audit combines the existing one-request exhaustive domain with a separate
four-request domain whose alias supports overlap. The latter crosses all
nonempty explicit subfamilies with complete, mutated and partial targets and
six callers. Direct source equations and a separately implemented product
oracle check every binding and replay; no production evaluator or support
function is used by that oracle.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import protocol_grouped as implementation
from checker import Rejected


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "proofs" / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


overlap = module("caller_overlap_domain", "audit_support_overlap.py")
tiny = module("caller_tiny_domain", "protocol_family_audit.py")


def callers():
    return {
        "unrestricted": {"initial": 0, "transitions": [[0, 0, 0, 0]]},
        "probes_only": {"initial": 0, "transitions": [[0, 0, 0, None]]},
        "three_ticks_then_probes": {"initial": 0, "transitions": [
            [None, None, None, 1], [None, None, None, 2],
            [None, None, None, 3], [3, 3, 3, None]]},
        "alternating_tick_probe": {"initial": 0, "transitions": [
            [None, None, None, 1], [0, 0, 0, None]]},
        "one_event": {"initial": 0, "transitions": [[1, 1, 1, 1], [None] * 4]},
        "inactive": {"initial": 0, "transitions": [[None] * 4]},
    }


def targets():
    yield from overlap.targets()
    for state in range(4):
        for request in range(4):
            changed = overlap.baseline_target()
            changed["transitions"][state][request] = None
            yield {"id": f"missing-{state}-{request}",
                   "perturbation": {"state": state, "request": request, "field": "absent"},
                   "machine": changed}


def admission(machine, protocol):
    """Compute closure by repeated set expansion, independently of engine BFS."""
    reached = {(machine["initial"], protocol["initial"])}
    seen_event = False
    while True:
        following = set(reached)
        for q, t in reached:
            for index, next_t in enumerate(protocol["transitions"][t]):
                if next_t is None:
                    continue
                seen_event = True
                edge = machine["transitions"][q][index]
                if edge is None:
                    return "missing"
                following.add((edge[1], next_t))
        if following == reached:
            return "admitted" if seen_event else "inactive"
        reached = following


def oracle_profile(machine, protocol, binding):
    """Search explicit source/target/caller triples using direct source equations."""
    if machine["observations"][machine["initial"]] != 0:
        return {"binding": binding, "equivalent": False, "length": 0,
                "indices": [], "trace": [], "reason": "initial observation"}
    start = (0, machine["initial"], protocol["initial"])
    queue, visited = deque([(start, [])]), {start}
    selected = None
    while queue and selected is None:
        (source, target, caller), prefix = queue.popleft()
        for index, action in enumerate(overlap.ACTIONS):
            next_caller = protocol["transitions"][caller][index]
            if next_caller is None:
                continue
            edge = machine["transitions"][target][index]
            if edge is None:
                raise AssertionError("oracle called on an unadmitted graph")
            actual = overlap.source_cell(source, action, binding)
            observed = (edge[0], machine["observations"][edge[1]])
            if actual != observed:
                selected = prefix + [index]
                break
            following = (actual[1], edge[1], next_caller)
            if following not in visited:
                visited.add(following)
                queue.append((following, prefix + [index]))
    if selected is None:
        return {"binding": binding, "equivalent": True,
                "length": None, "indices": None, "trace": None}
    source, target, caller = start
    trace = []
    final_target = final_caller = final_request = None
    for index in selected:
        edge = machine["transitions"][target][index]
        actual = overlap.source_cell(source, overlap.ACTIONS[index], binding)
        observed = (edge[0], machine["observations"][edge[1]])
        trace.append({
            "request": machine["alphabet"][index], "binding": binding,
            "source_state": source, "target_state": target, "protocol_state": caller,
            "source": list(actual), "target": list(observed),
            "decision_equal": actual[0] == observed[0],
            "state_equal": actual[1] == observed[1], "compared_equal": actual == observed,
        })
        final_target, final_caller, final_request = target, caller, index
        source, target, caller = actual[1], edge[1], protocol["transitions"][caller][index]
    return {"binding": binding, "equivalent": False, "length": len(selected),
            "indices": selected, "trace": trace, "target_state": final_target,
            "protocol_state": final_caller, "request": final_request}


def check_report(report, expected):
    if report["profiles"] != expected:
        raise AssertionError("caller profile or fixed-binding replay differs from independent equations")
    matches = [row["binding"] for row in expected if row["equivalent"]]
    failed = [row for row in expected if not row["equivalent"]]
    classification = "all" if not failed else "none" if not matches else "some"
    wanted = {"classification": classification, "bindings": len(expected),
              "matching_bindings": len(matches), "matching_family": matches,
              "failing_bindings": len(failed),
              "shortest_failure": min(row["length"] for row in failed) if failed else None,
              "strata": dict(Counter("infinity" if row["equivalent"] else str(row["length"])
                                     for row in expected))}
    if any(report[key] != value for key, value in wanted.items()):
        raise AssertionError("caller profile aggregate differs from its independently checked rows")
    return wanted


def controls():
    p, m = overlap.policy(), overlap.baseline_target()
    protocols = callers()
    rows = []
    original_step = implementation.reference_step
    cache = {}
    def stale_step(policy, state, request, binding):
        dependencies = tuple(implementation.support(policy, state, request))
        key = (dependencies, tuple(binding[name] for name in dependencies))
        if key not in cache:
            cache[key] = original_step(policy, state, request, binding)
        return cache[key]
    scenarios = [
        ("omitted_support", patch.object(implementation, "support", return_value=[]), 255, "unrestricted"),
        ("stale_cell_result", patch.object(implementation, "reference_step", side_effect=stale_step), 255, "unrestricted"),
    ]
    for name, mutation, mask, caller_name in scenarios:
        expected = [oracle_profile(m, protocols[caller_name], binding) for binding in overlap.family(mask)]
        detected, stage = False, None
        try:
            with mutation:
                result = implementation.support_indexed_protocol_profile(p, m, protocols[caller_name], overlap.family(mask))
            check_report(result, expected)
        except (AssertionError, Rejected):
            detected, stage = True, "profile-or-replay-check"
        rows.append({"fault": name, "detected": detected, "detection": stage})
    # Erasing caller history permits a two-step word when the supplied caller
    # requires three ticks before a probe. The independently checked word changes.
    restricted = protocols["three_ticks_then_probes"]
    expected = [oracle_profile(m, restricted, b) for b in overlap.BINDINGS]
    result = implementation.support_indexed_protocol_profile(p, m, protocols["unrestricted"], overlap.BINDINGS)
    detected = False
    try:
        check_report(result, expected)
    except AssertionError:
        detected = True
    rows.append({"fault": "erased_caller_history", "detected": detected, "detection": "independent-profile-check"})
    # Execute a faulty admission routine that fills a later missing edge.
    # An earlier universal difference then hides the missing edge from the
    # diagnosis loop, so the independent admission check must reject the result.
    partial = deepcopy(m)
    partial["transitions"][0][0][0] = "deny"
    partial["transitions"][3][1] = None
    original_graph = implementation._reachable_product
    def completed_graph(machine, protocol, work):
        filled = deepcopy(machine)
        for state, row in enumerate(filled["transitions"]):
            for index, edge in enumerate(row):
                if edge is None:
                    row[index] = ["deny", state]
        return original_graph(filled, protocol, work)
    with patch.object(implementation, "_reachable_product", side_effect=completed_graph):
        premature = implementation.support_indexed_protocol_profile(
            p, partial, protocols["unrestricted"], overlap.BINDINGS)
    rows.append({"fault": "classify_before_full_admission",
                 "detected": (premature["classification"] == "none" and
                              admission(partial, protocols["unrestricted"]) == "missing"),
                 "detection": "independent-admission-check"})
    if not all(row["detected"] for row in rows):
        raise AssertionError("an audit control was not detected")
    return rows


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # The old domain's independent direct-word oracle is reused unchanged;
    # only the subject being checked is replaced by the grouped algorithm.
    tiny_counts, tiny_cases, tiny_rows = Counter(), 0, 0
    with patch.object(tiny, "protocol_binding_profile", implementation.support_indexed_protocol_profile):
        with gzip.GzipFile(filename=str(output / "one-request-cases.jsonl.gz"), mode="wb", mtime=0) as stream:
            for i, left in enumerate(tiny.reference_tables()):
                for j, right in enumerate(tiny.reference_tables()):
                    for k, target in enumerate(tiny.target_tables()):
                        for l, caller in enumerate(tiny.caller_tables()):
                            checked = tiny.compare_case(left, right, target, caller)
                            row = {"references": [i, j], "target": k, "caller": l, **checked}
                            stream.write((json.dumps(row, sort_keys=True) + "\n").encode())
                            tiny_cases += 1
                            tiny_counts[checked.get("classification", checked.get("admission"))] += 1
                            tiny_rows += len(checked.get("lengths", []))
    p, all_targets, protocols = overlap.policy(), list(targets()), callers()
    write_json(output / "domain.json", {"policy": p, "bindings": overlap.BINDINGS,
                                       "callers": protocols, "targets": all_targets})
    counts, by_caller, lengths = Counter(), {name: Counter() for name in protocols}, Counter()
    cases = binding_rows = replay_rows = oracle_answers = 0
    with gzip.GzipFile(filename=str(output / "overlap-cases.jsonl.gz"), mode="wb", mtime=0) as stream:
        for target in all_targets:
            machine = target["machine"]
            for caller_name, protocol in protocols.items():
                admitted = admission(machine, protocol)
                expected_all = ([oracle_profile(machine, protocol, binding) for binding in overlap.BINDINGS]
                                if admitted == "admitted" else None)
                oracle_answers += len(expected_all) if expected_all is not None else 0
                for mask in range(1, 256):
                    family = overlap.family(mask)
                    try:
                        report = implementation.support_indexed_protocol_profile(p, machine, protocol, family)
                    except Rejected as error:
                        if admitted == "admitted" or error.kind != "inconclusive":
                            raise AssertionError("grouped engine rejected a complete admitted case") from error
                        checked = {"admission": admitted}
                        outcome = admitted
                    else:
                        if admitted != "admitted":
                            raise AssertionError("grouped engine classified an incomplete or inactive caller")
                        expected = [row for i, row in enumerate(expected_all) if mask & (1 << i)]
                        checked = check_report(report, expected)
                        checked["profiles"] = report["profiles"]
                        checked["representative_evaluations"] = report["transition_evaluations"]
                        outcome = checked["classification"]
                        binding_rows += len(expected)
                        for row in expected:
                            lengths["infinity" if row["equivalent"] else str(row["length"])] += 1
                            replay_rows += len(row["trace"] or [])
                    stream.write((json.dumps({"target": target["id"], "caller": caller_name,
                                               "family_mask": mask, **checked}, sort_keys=True) + "\n").encode())
                    counts[outcome] += 1
                    by_caller[caller_name][outcome] += 1
                    cases += 1
    summary = {
        "all_comparisons_passed": True,
        "one_request": {"family_cases": tiny_cases, "outcomes": dict(tiny_counts),
                        "classified_binding_rows": tiny_rows},
        "overlapping_supports": {
            "target_tables": len(all_targets), "caller_protocols": len(protocols),
            "nonempty_subfamilies": 255, "family_cases": cases,
            "outcomes": dict(counts), "by_caller": {k: dict(v) for k, v in by_caller.items()},
            "distinct_admitted_target_caller_binding_answers": oracle_answers,
            "classified_binding_rows_across_families": binding_rows,
            "replay_rows_across_families": replay_rows,
            "shortest_lengths_across_families": dict(lengths),
        },
        "controls": controls(),
        "oracle": "direct source equations; independent admission closure and explicit source/target/caller search",
    }
    if tiny_cases != 18225 or cases != 81 * 6 * 255:
        raise AssertionError("audit enumeration is incomplete")
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
