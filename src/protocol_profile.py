"""Fixed-binding diagnosis on a shared target/caller reachability graph.

The caller protocol is deterministic, partial and independent of the binding.
The target exposes every declared policy-state bit. Under these conditions the
first differing target/caller cell for a binding has a shortest admitted replay.
The module does not infer a caller protocol or a state decoder from observations.

An enabled target edge must be present before complete-family classification.
Absent edges and a protocol admitting no nonempty word are inconclusive. An
initial observation disagreement is already a complete empty-word witness and
is reported before this nonempty-event admission check.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable

from checker import Rejected, ensure, inspect_machine, inspect_policy, reference_step
from extensions import (DEFAULT_FAMILY_LIMIT, DEFAULT_WORK_BUDGET, _WorkBudget,
                        _normalize_family)


def _inspect_partial_interface(policy, machine, protocol):
    """Validate without interpreting an absent edge as an executable denial."""
    ensure(isinstance(machine, dict) and isinstance(machine.get("transitions"), list),
           "protocol profile needs explicit target rows")
    filled = []
    for q, row in enumerate(machine["transitions"]):
        ensure(isinstance(row, list), "invalid partial target row")
        filled.append([["deny", q] if edge is None else edge for edge in row])
    # These replacements are used only by the structural schema validator.
    inspect_machine(policy, {**machine, "transitions": filled}, compare_initial=False)
    ensure(isinstance(protocol, dict) and set(protocol) == {"initial", "transitions"},
           "invalid caller protocol fields")
    rows = protocol["transitions"]
    ensure(isinstance(rows, list) and 1 <= len(rows) <= 16,
           "caller protocol state bound")
    ensure(type(protocol["initial"]) is int and 0 <= protocol["initial"] < len(rows),
           "invalid caller protocol initial state")
    width = len(machine["alphabet"])
    for row in rows:
        ensure(isinstance(row, list) and len(row) == width,
               "caller protocol alphabet differs")
        ensure(all(value is None or (type(value) is int and 0 <= value < len(rows))
                   for value in row), "invalid caller protocol destination")


def _indices_to(parents, node):
    word = []
    while parents[node] is not None:
        node, index = parents[node]
        word.append(index)
    word.reverse()
    return word


def _reachable_product(machine, protocol, work):
    """Build one breadth-first graph independent of every reference binding."""
    first = (machine["initial"], protocol["initial"])
    parents, waiting, cells = {first: None}, deque([first]), []
    scanned = disabled = excluded_missing = 0
    while waiting:
        q, t = current = waiting.popleft()
        for index in range(len(machine["alphabet"])):
            work.charge(category="graph_cells")
            scanned += 1
            next_t = protocol["transitions"][t][index]
            edge = machine["transitions"][q][index]
            if next_t is None:
                disabled += 1
                excluded_missing += int(edge is None)
                continue
            if edge is None:
                error = Rejected("missing target edge on an admitted caller path", "inconclusive")
                error.details = {
                    "indices": _indices_to(parents, current) + [index],
                    "target_state": q, "protocol_state": t,
                    "reason": "incomplete target interface, not a semantic counterexample",
                    **work.report(),
                }
                raise error
            cells.append((q, t, index))
            following = (edge[1], next_t)
            if following not in parents:
                parents[following] = (current, index)
                waiting.append(following)
    ensure(cells, "caller protocol admits no checked component event", "inconclusive")
    return parents, cells, {
        "graph_traversals": 1,
        "target_protocol_reachable_states": len(parents),
        "target_reachable_states": len({q for q, _ in parents}),
        "graph_cells_inspected": scanned,
        "graph_enabled_edges": len(cells),
        "protocol_disabled_cells": disabled,
        "protocol_excluded_missing_cells": excluded_missing,
    }


def _replay(policy, machine, protocol, binding, indices, work):
    source = sum(1 << i for i, (_, value) in enumerate(policy["state"]) if value)
    q, t = machine["initial"], protocol["initial"]
    rows = []
    for index in indices:
        work.charge(category="replay_steps")
        request = machine["alphabet"][index]
        next_t = protocol["transitions"][t][index]
        edge = machine["transitions"][q][index]
        ensure(next_t is not None and edge is not None,
               "internal protocol replay traversed an absent edge")
        actual = reference_step(policy, source, request, binding)
        expected = (edge[0], machine["observations"][edge[1]])
        rows.append({
            "request": list(request), "binding": dict(binding),
            "source_state": source, "target_state": q, "protocol_state": t,
            "source": list(actual), "target": list(expected),
            "decision_equal": actual[0] == expected[0],
            "state_equal": actual[1] == expected[1],
            "compared_equal": actual == expected,
        })
        source, q, t = actual[1], edge[1], next_t
    return rows


def protocol_binding_profile(
    policy: dict[str, Any],
    machine: dict[str, Any],
    protocol: dict[str, Any],
    family: Iterable[dict[str, str]] | None = None,
    budget: int = DEFAULT_WORK_BUDGET,
    family_limit: int = DEFAULT_FAMILY_LIMIT,
) -> dict[str, Any]:
    """Return matching bindings and shortest admitted failures for all others.

    ``family=None`` uses the declared Cartesian family; an explicit finite
    family is validated and deduplicated without adding illegal combinations.
    The graph is traversed once. Each binding scans its enabled cells in
    breadth-first order until the first mismatch, then replays that word from
    the actual initial source state with the same binding at every step.

    Work units are family inputs, target/caller cells inspected (including
    disabled requests), reference transitions evaluated during diagnosis,
    and reference transitions evaluated during witness replay. They are
    reported separately; no symbolic or local-support evaluation is implied.
    Bounded schema validation is not included in this counter.

    Raises ``Rejected(kind='inconclusive')`` for incomplete admitted edges,
    no admitted nonempty word, or an exhausted work/family envelope. This
    routine returns no partial matching family in these cases. A proven
    initial disagreement is reported without traversing the target graph.
    """
    inspect_policy(policy)
    _inspect_partial_interface(policy, machine, protocol)
    work = _WorkBudget(budget)
    bindings = _normalize_family(policy, family, work, family_limit)
    source_initial = sum(1 << i for i, (_, value) in enumerate(policy["state"]) if value)
    target_initial = machine["observations"][machine["initial"]]
    profiles = []
    evaluations = 0
    if source_initial != target_initial:
        graph = {
            "graph_traversals": 0, "target_protocol_reachable_states": None,
            "target_reachable_states": None, "graph_cells_inspected": 0,
            "graph_enabled_edges": 0, "protocol_disabled_cells": 0,
            "protocol_excluded_missing_cells": 0,
        }
        profiles = [{
            "binding": binding, "equivalent": False, "length": 0,
            "indices": [], "trace": [], "reason": "initial observation",
        } for binding in bindings]
    else:
        parents, cells, graph = _reachable_product(machine, protocol, work)
        for binding in bindings:
            witness = None
            for q, t, index in cells:
                work.charge(category="semantic_steps")
                evaluations += 1
                request = machine["alphabet"][index]
                actual = reference_step(policy, machine["observations"][q], request, binding)
                edge = machine["transitions"][q][index]
                expected = (edge[0], machine["observations"][edge[1]])
                if actual != expected:
                    indices = _indices_to(parents, (q, t)) + [index]
                    replay = _replay(policy, machine, protocol, binding, indices, work)
                    ensure(replay and not replay[-1]["compared_equal"],
                           "internal protocol profile replay has no final disagreement")
                    ensure(all(row["compared_equal"] for row in replay[:-1]),
                           "internal protocol profile replay differs before its selected cell")
                    ensure(len(indices) <= len(parents),
                           "internal protocol profile exceeded the reachable-product bound")
                    witness = {
                        "binding": binding, "equivalent": False,
                        "length": len(indices), "indices": indices, "trace": replay,
                        "target_state": q, "protocol_state": t, "request": index,
                    }
                    break
            profiles.append(witness if witness is not None else {
                "binding": binding, "equivalent": True, "length": None,
                "indices": None, "trace": None,
            })
    matching = [row["binding"] for row in profiles if row["equivalent"]]
    failing = [row for row in profiles if not row["equivalent"]]
    strata: dict[str, int] = {}
    for row in profiles:
        key = "infinity" if row["equivalent"] else str(row["length"])
        strata[key] = strata.get(key, 0) + 1
    return {
        "status": "equivalent" if not failing else "mismatch",
        "accepted": not failing,
        "classification": "all" if not failing else "none" if not matching else "some",
        "bindings": len(profiles), "matching_bindings": len(matching),
        "failing_bindings": len(failing), "matching_family": matching,
        "shortest_failure": min(row["length"] for row in failing) if failing else None,
        "strata": strata, "profiles": profiles, **graph,
        "transition_evaluations": evaluations,
        "replay_evaluations": work.categories.get("replay_steps", 0),
        **work.report(),
        "scope": "fixed binding family, complete declared policy state, given regular caller protocol",
        "unconditional_external_api_refinement": False,
    }
