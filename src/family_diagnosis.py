"""Support-indexed complete diagnosis for a finite family of fixed bindings.

Reachability and first-failure order are the same as ``extensions.binding_profile``.
At each target cell, surviving bindings are grouped by the cell's syntactic
support. One legal member represents each group for that transition only.
A failing group retires, with a separate fixed-binding replay for every member.

This reduces repeated reference evaluations when many bindings agree on local
support. It still constructs bounded family indexes, updates their memberships,
and emits one result per binding. Those costs are counted separately.
"""
from __future__ import annotations

from typing import Any, Iterable

from checker import ensure, inspect_machine, inspect_policy, reference_step, support
from extensions import (DEFAULT_FAMILY_LIMIT, DEFAULT_WORK_BUDGET, _WorkBudget,
                        _initial, _normalize_family, _reference_replay, _target_paths)


def support_indexed_profile(
    policy: dict[str, Any],
    machine: dict[str, Any],
    family: Iterable[dict[str, str]] | None = None,
    budget: int = DEFAULT_WORK_BUDGET,
    family_limit: int = DEFAULT_FAMILY_LIMIT,
) -> dict[str, Any]:
    """Classify the full fixed-binding family using active support projections.

    Semantic profile rows, BFS tie-breaking, and witness replay format match
    ``binding_profile``. The same graph is shared across all bindings. A cached
    index for a support tuple contains only still-active bindings; retirement
    updates every already-built index. The representative is always an actual
    legal family member, including for a correlated explicitly supplied family.

    ``transition_evaluations`` counts representative calls to the reference
    transition function, excluding the separately reported replay calls.
    Projection construction, coordinate reads, membership updates, group visits,
    support scans and output rows are separately charged to the work envelope.
    These abstract units are not interchangeable with elapsed time.
    """
    inspect_policy(policy)
    inspect_machine(policy, machine, compare_initial=False)
    work = _WorkBudget(budget)
    bindings = _normalize_family(policy, family, work, family_limit)
    paths = _target_paths(machine, work)
    source_initial = _initial(policy)
    target_initial = machine["observations"][machine["initial"]]
    profiles: list[dict[str, Any] | None] = [None] * len(bindings)
    active = dict.fromkeys(range(len(bindings)))
    # support tuple -> projection -> insertion-ordered active binding ids
    indexes: dict[tuple[str, ...], dict[tuple[str, ...], dict[int, None]]] = {}
    evaluations = support_queries = projection_evaluations = projection_coordinates = 0
    created = removed = live_memberships = peak_memberships = 0
    group_visits = cached_groups = peak_groups = 0
    support_guard_atoms = sum(len(rule["guard"]) for rule in policy["rules"])

    def project(binding_id, dependencies):
        nonlocal projection_evaluations, projection_coordinates
        work.charge(category="family_projections")
        work.charge(len(dependencies), category="projection_coordinates")
        projection_evaluations += 1
        projection_coordinates += len(dependencies)
        return tuple(bindings[binding_id][name] for name in dependencies)

    def retire(binding_id):
        nonlocal removed, live_memberships, cached_groups
        ensure(binding_id in active, "internal support profile retired an inactive binding")
        del active[binding_id]
        for dependencies, groups in indexes.items():
            key = project(binding_id, dependencies)
            ensure(key in groups and binding_id in groups[key],
                   "internal support index lost an active member")
            work.charge(category="index_memberships_removed")
            removed += 1
            live_memberships -= 1
            del groups[key][binding_id]
            if not groups[key]:
                del groups[key]
                cached_groups -= 1

    if source_initial != target_initial:
        for binding_id, binding in enumerate(bindings):
            work.charge(category="output_rows")
            profiles[binding_id] = {
                "binding": binding, "equivalent": False, "length": 0,
                "indices": [], "trace": [], "reason": "initial observation",
            }
        active.clear()
    else:
        for q, prefix in paths.items():
            if not active:
                break
            state = machine["observations"][q]
            for index, request in enumerate(machine["alphabet"]):
                if not active:
                    break
                work.charge(category="support_queries")
                work.charge(support_guard_atoms, category="support_guard_atoms")
                support_queries += 1
                dependencies = tuple(support(policy, state, request))
                if dependencies not in indexes:
                    groups: dict[tuple[str, ...], dict[int, None]] = {}
                    for binding_id in active:
                        key = project(binding_id, dependencies)
                        if key not in groups:
                            groups[key] = {}
                            cached_groups += 1
                        groups[key][binding_id] = None
                        work.charge(category="index_memberships_created")
                        created += 1
                        live_memberships += 1
                    indexes[dependencies] = groups
                    peak_memberships = max(peak_memberships, live_memberships)
                    peak_groups = max(peak_groups, cached_groups)
                groups = indexes[dependencies]
                edge = machine["transitions"][q][index]
                expected = (edge[0], machine["observations"][edge[1]])
                # Retirement deletes the current group from every cached index.
                for key in list(groups):
                    group = groups[key]
                    work.charge(category="active_group_visits")
                    work.charge(category="semantic_steps")
                    group_visits += 1
                    evaluations += 1
                    representative = next(iter(group))
                    actual = reference_step(policy, state, request, bindings[representative])
                    if actual == expected:
                        continue
                    indices = prefix + [index]
                    for binding_id in list(group):
                        binding = bindings[binding_id]
                        replay = _reference_replay(policy, machine, indices,
                                                   [binding] * len(indices), work=work)
                        ensure(replay and not replay[-1]["compared_equal"],
                               "internal support profile replay has no final disagreement")
                        ensure(all(row["compared_equal"] for row in replay[:-1]),
                               "internal support profile replay differs before selected cell")
                        work.charge(category="output_rows")
                        profiles[binding_id] = {
                            "binding": binding, "equivalent": False,
                            "length": len(indices), "indices": indices, "trace": replay,
                            "target_state": q, "request": index,
                        }
                        retire(binding_id)
        for binding_id in active:
            work.charge(category="output_rows")
            profiles[binding_id] = {
                "binding": bindings[binding_id], "equivalent": True, "length": None,
                "indices": None, "trace": None,
            }
    ensure(all(row is not None for row in profiles), "internal support profile has an unclassified member")
    matching = sum(row["equivalent"] for row in profiles)
    finite = [row["length"] for row in profiles if not row["equivalent"]]
    strata: dict[str, int] = {}
    for row in profiles:
        key = "infinity" if row["equivalent"] else str(row["length"])
        strata[key] = strata.get(key, 0) + 1
    return {
        "classification": "all" if matching == len(profiles) else "none" if matching == 0 else "some",
        "bindings": len(profiles), "matching_bindings": matching,
        "failing_bindings": len(profiles) - matching,
        "shortest_failure": min(finite) if finite else None,
        "strata": strata, "target_reachable_states": len(paths),
        "transition_evaluations": evaluations, "profiles": profiles,
        "graph_traversals": 1,
        "graph_edges": work.categories.get("graph_edges", 0),
        "replay_evaluations": work.categories.get("replay_steps", 0),
        "support_queries": support_queries,
        "cached_supports": len(indexes),
        "family_projection_evaluations": projection_evaluations,
        "family_projection_coordinates": projection_coordinates,
        "index_memberships_created": created, "index_memberships_removed": removed,
        "active_group_visits": group_visits,
        "peak_cached_memberships": peak_memberships,
        "peak_active_groups": peak_groups,
        **work.report(),
    }
