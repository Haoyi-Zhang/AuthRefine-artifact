"""Active-support diagnosis for a fixed family under an explicit caller.

The target/caller graph is admitted in full before any nonempty diagnosis.
Its cells are processed in breadth-first order, sharing each reference step
among surviving bindings which agree on its support. Cached indexes retain
memberships, never results from an earlier cell. Witnesses keep one complete
binding throughout and include the actual caller history.
"""
from __future__ import annotations

from typing import Any, Iterable

from checker import ensure, inspect_policy, reference_step, support
from extensions import DEFAULT_FAMILY_LIMIT, DEFAULT_WORK_BUDGET, _WorkBudget, _normalize_family
from protocol_profile import (_indices_to, _inspect_partial_interface,
                              _reachable_product, _replay)


def support_indexed_protocol_profile(
    policy: dict[str, Any],
    machine: dict[str, Any],
    protocol: dict[str, Any],
    family: Iterable[dict[str, str]] | None = None,
    budget: int = DEFAULT_WORK_BUDGET,
    family_limit: int = DEFAULT_FAMILY_LIMIT,
) -> dict[str, Any]:
    """Return the same complete semantic profile as ``protocol_binding_profile``.

    Equal initial observations require complete target edges on every reachable
    enabled caller path, even if every binding would fail an earlier cell.
    Missing edges, an inactive caller and exhausted work bounds are
    inconclusive. An initial disagreement already supplies empty witnesses.

    Graph admission and deterministic BFS tie-breaking are shared with the
    ungrouped implementation. Diagnosis groups active legal family members by
    local support; it does not complete a correlated family to a product.
    All reference calls, support scans, projections, membership updates and
    replay/output operations have separate counters. Schema checks remain
    outside this abstract work envelope.
    """
    inspect_policy(policy)
    _inspect_partial_interface(policy, machine, protocol)
    work = _WorkBudget(budget)
    bindings = _normalize_family(policy, family, work, family_limit)
    source_initial = sum(1 << i for i, (_, value) in enumerate(policy["state"]) if value)
    target_initial = machine["observations"][machine["initial"]]
    profiles: list[dict[str, Any] | None] = [None] * len(bindings)
    active = dict.fromkeys(range(len(bindings)))
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
        ensure(binding_id in active, "internal caller grouping retired an inactive binding")
        del active[binding_id]
        for dependencies, groups in indexes.items():
            key = project(binding_id, dependencies)
            ensure(key in groups and binding_id in groups[key],
                   "internal caller support index lost an active member")
            work.charge(category="index_memberships_removed")
            removed += 1
            live_memberships -= 1
            del groups[key][binding_id]
            if not groups[key]:
                del groups[key]
                cached_groups -= 1

    if source_initial != target_initial:
        graph = {
            "graph_traversals": 0, "target_protocol_reachable_states": None,
            "target_reachable_states": None, "graph_cells_inspected": 0,
            "graph_enabled_edges": 0, "protocol_disabled_cells": 0,
            "protocol_excluded_missing_cells": 0,
        }
        for binding_id, binding in enumerate(bindings):
            work.charge(category="output_rows")
            profiles[binding_id] = {
                "binding": binding, "equivalent": False, "length": 0,
                "indices": [], "trace": [], "reason": "initial observation",
            }
        active.clear()
    else:
        parents, cells, graph = _reachable_product(machine, protocol, work)
        for q, t, index in cells:
            if not active:
                break
            state = machine["observations"][q]
            request = machine["alphabet"][index]
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
                indices = _indices_to(parents, (q, t)) + [index]
                for binding_id in list(group):
                    binding = bindings[binding_id]
                    replay = _replay(policy, machine, protocol, binding, indices, work)
                    ensure(replay and not replay[-1]["compared_equal"],
                           "internal grouped caller replay has no final disagreement")
                    ensure(all(row["compared_equal"] for row in replay[:-1]),
                           "internal grouped caller replay differs before its selected cell")
                    ensure(len(indices) <= len(parents),
                           "internal grouped caller replay exceeded the reachable-product bound")
                    work.charge(category="output_rows")
                    profiles[binding_id] = {
                        "binding": binding, "equivalent": False,
                        "length": len(indices), "indices": indices, "trace": replay,
                        "target_state": q, "protocol_state": t, "request": index,
                    }
                    retire(binding_id)
        for binding_id in active:
            work.charge(category="output_rows")
            profiles[binding_id] = {
                "binding": bindings[binding_id], "equivalent": True,
                "length": None, "indices": None, "trace": None,
            }
    ensure(all(row is not None for row in profiles),
           "internal grouped caller profile has an unclassified member")
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
        "support_queries": support_queries, "cached_supports": len(indexes),
        "family_projection_evaluations": projection_evaluations,
        "family_projection_coordinates": projection_coordinates,
        "index_memberships_created": created, "index_memberships_removed": removed,
        "active_group_visits": group_visits,
        "peak_cached_memberships": peak_memberships, "peak_active_groups": peak_groups,
        **work.report(),
        "scope": "fixed binding family, complete declared policy state, given regular caller protocol",
        "unconditional_external_api_refinement": False,
    }
