#!/usr/bin/env python3
"""Independent, bounded checks of AuthRefine's complete symbolic profiles.

Run with the isolated interpreter containing dd.cudd. The direct policy oracle
and its product BFS below do not call AuthRefine's reference evaluator,
compiler, grouping implementation, or profile traversal. Internal diagram
classes are deliberately exercised for the separate representation checks.
No project files or experiment records are modified.
"""
from __future__ import annotations

import argparse
from collections import deque
from importlib.metadata import version
import itertools
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(actual, expected, message):
    if actual != expected:
        raise AssertionError(f"{message}: actual={actual!r}; expected={expected!r}")


def check_family_encoding(sf, work_budget):
    axes = [
        {"name": name, "kind": "role", "candidates": [str(i) for i in range(size)]}
        for name, size in [("a", 3), ("b", 1), ("c", 5), ("d", 2)]
    ]
    legal = {
        (0, 0, 0, 0), (0, 0, 0, 1), (2, 0, 4, 0),
        (1, 0, 2, 1), (2, 0, 1, 1),
    }
    domain = set(itertools.product(range(3), range(1), range(5), range(2)))
    results = []
    for cls in (sf._FiniteDiagram, sf._CuddDiagram):
        diagram = cls(axes, 100_000, 2_000_000)
        root = sf._family_relation(diagram, sorted(legal), work_budget(100_000))
        equal(set(diagram.assignments(root)), legal, "exact correlated family")
        equal(set(diagram.assignments(diagram.domain())), domain, "finite domain")
        result = {
            "backend": diagram.metrics()["backend"], "axis_sizes": [3, 1, 5, 2],
            "family_members": len(legal), "domain_members": len(domain),
        }
        if cls is sf._CuddDiagram:
            variables = [name for axis in diagram.variables for name in axis]
            diagram.bdd.reorder({name: i for i, name in enumerate(reversed(variables))})
            equal(set(diagram.assignments(root)), legal, "family after CUDD reorder")
            encodings = 0
            for bits in itertools.product((False, True), repeat=len(variables)):
                assignment = dict(zip(variables, bits))
                decoded = tuple(
                    sum(int(assignment[name]) << bit for bit, name in enumerate(axis))
                    for axis in diagram.variables
                )
                equal(diagram.bdd.let(assignment, root) == diagram.true,
                      decoded in legal, "Boolean encoding after CUDD reorder")
                encodings += 1
            result.update(binary_variables=len(variables), binary_encodings=encodings,
                          forced_reverse_reorder=True,
                          dynamic_reordering=diagram.metrics()["dynamic_reordering"])
        results.append(result)
    return results


def mixed_sort_fixture():
    def atom(field, alias=None, name=None, neg=False):
        return {"field": field,
                **({"alias": alias} if alias is not None else {"name": name}),
                "negated": neg}

    policy = {
        "principals": ["u0", "u1", "u2"],
        "resources": ["o0", "o1", "o2"],
        "actions": ["a0", "a1", "a2"],
        "roles": ["r0", "r1", "r2", "r3", "r4"],
        "members": [["u0", "r0"], ["u0", "r2"], ["u1", "r1"],
                    ["u2", "r2"], ["u2", "r4"]],
        "state": [["p", False], ["q", True]],
        "aliases": [
            {"name": name, "kind": kind, "candidates": values}
            for name, kind, values in [
                ("act", "action", ["a0", "a1", "a2"]),
                ("obj", "resource", ["o0", "o1", "o2"]),
                ("rol", "role", ["r0", "r1", "r2", "r3", "r4"]),
                ("who", "principal", ["u0", "u1", "u2"]),
            ]
        ],
        "rules": [
            {"decision": "deny",
             "guard": [atom("principal", "who"), atom("resource", "obj", neg=True),
                       {"field": "state", "name": "p", "value": True}],
             "updates": []},
            {"decision": "allow",
             "guard": [atom("action", "act"), atom("role", "rol"),
                       {"field": "state", "name": "q", "value": True}],
             "updates": [{"name": "p", "from": "q", "negated": True},
                         {"name": "q", "from": "p", "negated": False}]},
            {"decision": "allow",
             "guard": [atom("resource", "obj"), atom("principal", name="u2")],
             "updates": [{"name": "p", "value": True}, {"name": "q", "value": False}]},
            {"decision": "deny",
             "guard": [atom("role", "rol", neg=True), atom("action", name="a1")],
             "updates": []},
            {"decision": "allow",
             "guard": [atom("principal", "who", neg=True),
                       {"field": "state", "name": "p", "value": False}],
             "updates": [{"name": "q", "from": "q", "negated": True}]},
        ],
    }
    family = [dict(zip([a["name"] for a in policy["aliases"]], values))
              for values in itertools.product(*(a["candidates"] for a in policy["aliases"]))]
    inputs = [list(v) for v in itertools.product(policy["principals"],
                                                policy["resources"], policy["actions"])]

    # Standalone direct equations: first matching rule, simultaneous old-state
    # updates, default denial. No subject evaluator or compiler is called.
    def step(state, request, binding):
        old = {"p": bool(state & 1), "q": bool(state & 2)}
        for rule in policy["rules"]:
            matched = True
            for value in rule["guard"]:
                if value["field"] == "state":
                    truth = old[value["name"]] == value["value"]
                else:
                    name = binding[value["alias"]] if "alias" in value else value["name"]
                    truth = ([request[0], name] in policy["members"]) if value["field"] == "role" else (
                        request[{"principal": 0, "resource": 1, "action": 2}[value["field"]]] == name
                    )
                    if value["negated"]:
                        truth = not truth
                if not truth:
                    matched = False
                    break
            if matched:
                after = old.copy()
                for effect in rule["updates"]:
                    after[effect["name"]] = effect["value"] if "value" in effect else (
                        not old[effect["from"]] if effect["negated"] else old[effect["from"]]
                    )
                return rule["decision"], int(after["p"]) + 2 * int(after["q"])
        return "deny", state

    machine = {
        "state_names": ["p", "q"], "alphabet": inputs, "initial": 2,
        "observations": [0, 1, 2, 3],
        "transitions": [[list(step(state, request, family[37])) for request in inputs]
                        for state in range(4)],
    }
    caller = {"initial": 0, "transitions": [
        [1 if x[2] != "a2" else None for x in inputs],
        [2 if x[1] != "o2" else None for x in inputs],
        [0 if x[0] != "u2" else None for x in inputs],
    ]}
    subfamily = [family[i] for i in [134, 0, 37, 44, 59, 83, 22, 111, 2, 61, 16, 78, 47]]
    return policy, family, inputs, step, machine, caller, subfamily


def check_mixed_sort_profiles(sf):
    policy, family, inputs, step, machine, caller, subfamily = mixed_sort_fixture()

    # Independent BFS keeps source, target and caller state. Equal prefixes
    # alone are extended, in request order, to select a canonical shortest word.
    def answer(binding, call):
        start = (2, machine["initial"], call["initial"])
        queue = deque([(start, [])])
        seen = {start}
        while queue:
            (source, target_state, phase), prefix = queue.popleft()
            for index, request in enumerate(inputs):
                next_phase = call["transitions"][phase][index]
                if next_phase is None:
                    continue
                actual = step(source, request, binding)
                edge = machine["transitions"][target_state][index]
                target = edge[0], machine["observations"][edge[1]]
                if actual != target:
                    return False, prefix + [index]
                following = actual[1], edge[1], next_phase
                if following not in seen:
                    seen.add(following)
                    queue.append((following, prefix + [index]))
        return True, None

    checked = replay_rows = 0
    runs = []
    for backend in ("finite-domain", "cudd"):
        for provided in (None, subfamily):
            allowed = family if provided is None else provided
            for protocol in (None, caller):
                call = protocol or {"initial": 0, "transitions": [[0] * len(inputs)]}
                report = sf.symbolic_family_profile(policy, machine, family=provided,
                                                     protocol=protocol, backend=backend)
                equal(len(report["profiles"]), len(allowed), "complete profile size")
                expected_matches = 0
                for binding, row in zip(allowed, report["profiles"]):
                    matches, word = answer(binding, call)
                    expected_matches += int(matches)
                    equal(row["binding"], binding, "input family order and binding")
                    equal((row["equivalent"], row["indices"]), (matches, word),
                          "direct-equation verdict and canonical shortest word")
                    equal(row["length"], None if word is None else len(word), "word length")
                    if word is None:
                        equal(row["trace"], None, "matching member has no failure trace")
                    else:
                        equal(len(row["trace"]), len(word), "complete replay length")
                        source, target_state, phase = 2, machine["initial"], call["initial"]
                        for position, (index, trace) in enumerate(zip(word, row["trace"])):
                            actual = step(source, inputs[index], binding)
                            edge = machine["transitions"][target_state][index]
                            target = edge[0], machine["observations"][edge[1]]
                            equal(trace["binding"], binding, "fixed-binding replay")
                            equal(trace["request"], inputs[index], "replay physical request")
                            equal(trace["source"], list(actual), "direct source replay")
                            equal(trace["target"], list(target), "direct target replay")
                            equal(trace["compared_equal"], actual == target, "replay equality flag")
                            equal(trace["compared_equal"], position < len(word) - 1,
                                  "first disagreement is the final replay row")
                            if protocol is not None:
                                equal((trace["source_state"], trace["target_state"], trace["protocol_state"]),
                                      (source, target_state, phase), "caller replay history")
                            source, target_state, phase = actual[1], edge[1], call["transitions"][phase][index]
                            replay_rows += 1
                    checked += 1
                equal(report["matching_bindings"], expected_matches, "matching count")
                equal(report["classification"],
                      "all" if expected_matches == len(allowed) else "none" if expected_matches == 0 else "some",
                      "family classification")
                runs.append({"backend": backend, "family_size": len(allowed),
                             "caller": "three-phase partial" if protocol else "unrestricted",
                             "matching": expected_matches, "excluded": len(allowed) - expected_matches})
    equal(checked, 592, "bounded independent binding-result comparison count")
    return {"profile_runs": len(runs), "binding_results_checked": checked,
            "replay_rows_checked": replay_rows, "runs": runs}


def check_admission_and_budgets(sf, rejected):
    policy = {
        "principals": ["u"], "resources": ["o"], "actions": ["a", "b"],
        "roles": ["r", "s", "t"], "members": [], "state": [],
        "aliases": [{"name": name, "kind": "role", "candidates": ["r", "s", "t"]}
                    for name in ["x", "y"]],
        "rules": [{"decision": "allow", "guard": [], "updates": []}],
    }
    machine = {
        "state_names": [], "alphabet": [["u", "o", "a"], ["u", "o", "b"]],
        "observations": [0, 0, 0, 0], "initial": 0,
        "transitions": [
            [["deny", 0], ["allow", 1]], [["allow", 1], ["allow", 2]],
            [["allow", 2], ["allow", 3]], [["allow", 3], ["allow", 3]],
        ],
    }
    family = [{"x": "t", "y": "r"}, {"x": "r", "y": "t"},
              {"x": "s", "y": "s"}, {"x": "r", "y": "r"}]
    results = []
    for backend in ("finite-domain", "cudd"):
        original = sf._mismatch
        calls = []

        def once(*args, **kwargs):
            calls.append(1)
            equal(len(calls), 1, "no semantic work after universal exclusion")
            return original(*args, **kwargs)

        with patch.object(sf, "_mismatch", side_effect=once):
            report = sf.symbolic_family_profile(policy, machine, family=family, backend=backend)
        equal(report["classification"], "none", "universal exclusion")
        equal(len(calls), 1, "one symbolic mismatch predicate")
        equal(report["graph_cells_inspected"], 8, "full graph admission before classification")
        equal([row["binding"] for row in report["profiles"]], family, "input family order")
        for row in report["profiles"]:
            equal((row["indices"], row["length"]), ([0], 1), "early-stop selected witness")
            equal(row["trace"][0]["compared_equal"], False, "early-stop disagreement")

        work = report["work_operations"]
        operations = report["symbolic"]["conditional_operations"]
        exact = sf.symbolic_family_profile(policy, machine, family=family, backend=backend,
                                           budget=work, operation_limit=operations)
        equal(exact["profiles"], report["profiles"], "exact work and ITE caps succeed")
        rejected_limits = []
        for limits in [{"budget": work - 1}, {"operation_limit": operations - 1}]:
            try:
                sf.symbolic_family_profile(policy, machine, family=family, backend=backend, **limits)
            except rejected as error:
                equal(error.kind, "inconclusive", "below-cap rejection kind")
                rejected_limits.append(limits)
            else:
                raise AssertionError("insufficient budget returned a family profile")

        partial = {**machine, "transitions": [[list(edge) for edge in row]
                                               for row in machine["transitions"]]}
        partial["transitions"][3][0] = None
        with patch.object(sf, "_mismatch", side_effect=AssertionError("classification preceded admission")):
            try:
                sf.symbolic_family_profile(policy, partial, family=family,
                                           protocol={"initial": 0, "transitions": [[0, 0]]},
                                           backend=backend)
            except rejected as error:
                equal(error.kind, "inconclusive", "late missing edge rejection kind")
                equal(error.details["indices"], [1, 1, 1, 0], "late missing edge path")
            else:
                raise AssertionError("admitted late missing edge was accepted")
        results.append({"backend": backend, "admitted_graph_cells": 8,
                        "mismatch_calls_before_universal_exclusion": 1,
                        "excluded_family_members": 4, "exact_work_cap": work,
                        "exact_conditional_operation_cap": operations,
                        "conditional_operation_unit": report["symbolic"]["operation_unit"],
                        "below_cap_rejections": rejected_limits,
                        "missing_edge_path": [1, 1, 1, 0]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path,
                        default=Path(__file__).resolve().parents[1],
                        help="artifact root (or a directory containing artifact/)")
    arguments = parser.parse_args()
    project = arguments.project.resolve()
    artifact = project / "artifact" if (project / "artifact/src").is_dir() else project
    require((artifact / "src/symbolic_family.py").is_file(), "project module is missing")
    sys.path[:0] = [str(artifact / "src"), str(artifact)]
    import symbolic_family as sf
    from extensions import _WorkBudget
    from checker import Rejected
    from dd.cudd import BDD  # Require the real CUDD extension; do not silently skip.
    require(BDD is not None, "compiled CUDD extension is unavailable")
    results = {
        "status": "passed",
        "runtime": {"python": sys.version.split()[0], "dd": version("dd")},
        "family_encoding": check_family_encoding(sf, _WorkBudget),
        "independent_profiles": check_mixed_sort_profiles(sf),
        "admission_and_budgets": check_admission_and_budgets(sf, Rejected),
        "limits": [
            "These are bounded independent examples, not verification of every policy or implementation path.",
            "CUDD node_limit is checked after each Boolean ITE returns; it is not a transient-allocation or memory ceiling.",
            "Finite-domain recursive ITE invocations and CUDD Boolean ITE interface calls are different units.",
        ],
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
