"""Complete finite-family diagnosis with reduced decision diagrams.

The legal supplied family is encoded before traversal; no Cartesian completion
or post-hoc removal of illegal interpretations is performed. Disjoint regions
record the first bad cell in the common BFS order. Every excluded member is
materialized with its own fixed-binding replay. The optional CUDD backend uses
the same Boolean construction as the portable finite-domain backend.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from checker import Rejected, ensure, inspect_machine, inspect_policy
from extensions import (DEFAULT_FAMILY_LIMIT, DEFAULT_WORK_BUDGET, _WorkBudget,
                        _normalize_family, _reference_replay)
from protocol_profile import (_indices_to, _inspect_partial_interface,
                              _reachable_product, _replay)
from symbolic import Diagram


class _FiniteDiagram:
    def __init__(self, aliases, node_limit, operation_limit):
        self.aliases = aliases
        self.diagram = Diagram(aliases, node_limit, operation_limit)
        self.false, self.true = self.diagram.false, self.diagram.true

    def constant(self, value):
        return self.true if value else self.false

    def choice(self, level, children):
        return self.diagram.node(level, children)

    def ite(self, guard, yes, no):
        return self.diagram.ite(guard, yes, no)

    def domain(self):
        return self.true

    def assignments(self, root):
        """Enumerate only satisfying finite-domain assignments, including skips."""
        def visit(node, level, prefix):
            if node == self.false:
                return
            if level == len(self.aliases):
                ensure(node == self.true, "symbolic non-Boolean family terminal")
                yield prefix
                return
            node_level, children = self.diagram.nodes[node]
            for index in range(len(self.aliases[level]["candidates"])):
                following = children[index] if node_level == level else node
                yield from visit(following, level + 1, prefix + (index,))
        yield from visit(root, 0, ())

    def metrics(self):
        return {"backend": "finite-domain", "nodes": len(self.diagram.nodes),
                "conditional_operations": self.diagram.operations,
                "operation_unit": "recursive finite-domain ITE invocations"}


class _CuddDiagram:
    def __init__(self, aliases, node_limit, operation_limit):
        try:
            from dd.cudd import BDD
        except ImportError as error:
            raise Rejected("CUDD backend requires the supplied symbolic dependencies",
                           "inconclusive") from error
        self.aliases = aliases
        self.bdd = BDD()
        self.node_limit, self.operation_limit = node_limit, operation_limit
        self.operations = 0
        self.peak_nodes = len(self.bdd)
        self.variables = [[f"a{i}_b{j}" for j in range((len(a["candidates"]) - 1).bit_length())]
                          for i, a in enumerate(aliases)]
        names = [name for axis in self.variables for name in axis]
        if names:
            self.bdd.declare(*names)
        self.false, self.true = self.bdd.false, self.bdd.true
        self.equalities = []
        self.legal_domain = self.true
        for axis, alias in zip(self.variables, aliases):
            choices = []
            for value in range(len(alias["candidates"])):
                term = self.true
                for bit, name in enumerate(axis):
                    variable = self.bdd.var(name)
                    term = self.ite(variable, term, self.false) if (value >> bit) & 1 else self.ite(variable, self.false, term)
                choices.append(term)
            self.equalities.append(choices)
            domain = self.false
            for term in choices:
                domain = self.ite(term, self.true, domain)
            self.legal_domain = self.ite(domain, self.legal_domain, self.false)
        self.configuration = self.bdd.configure()

    def constant(self, value):
        return self.true if value else self.false

    def ite(self, guard, yes, no):
        self.operations += 1
        ensure(self.operations <= self.operation_limit, "CUDD operation budget", "inconclusive")
        result = self.bdd.ite(guard, yes, no)
        self.peak_nodes = max(self.peak_nodes, len(self.bdd))
        ensure(self.peak_nodes <= self.node_limit, "CUDD node budget", "inconclusive")
        return result

    def choice(self, level, children):
        result = self.false
        for equal, child in zip(self.equalities[level], children):
            result = self.ite(equal, child, result)
        return result

    def domain(self):
        return self.legal_domain

    def assignments(self, root):
        variables = {name for axis in self.variables for name in axis}
        for assignment in self.bdd.pick_iter(root, care_vars=variables):
            values = tuple(sum(int(assignment[name]) << bit for bit, name in enumerate(axis))
                           for axis in self.variables)
            ensure(all(value < len(alias["candidates"])
                       for value, alias in zip(values, self.aliases)),
                   "symbolic family contains an invalid binary encoding")
            yield values

    def metrics(self):
        return {"backend": "cudd", "nodes": len(self.bdd), "peak_nodes": self.peak_nodes,
                "conditional_operations": self.operations,
                "operation_unit": "calls to the CUDD Boolean ITE interface",
                "dynamic_reordering": self.configuration["reordering"],
                "binary_variables": sum(map(len, self.variables))}


def _family_relation(diagram, assignments, work):
    """Build the exact relation from a trie of legal rows, without a product."""
    def build(level, rows):
        work.charge(category="family_relation_nodes")
        if level == len(diagram.aliases):
            return diagram.true
        groups = defaultdict(list)
        for row in rows:
            work.charge(category="family_relation_coordinates")
            groups[row[level]].append(row)
        children = [build(level + 1, groups[value]) if value in groups else diagram.false
                    for value in range(len(diagram.aliases[level]["candidates"]))]
        return diagram.choice(level, children)
    return build(0, assignments)


def _mismatch(diagram, policy, state, request, expected, work):
    """Compile first-match rule semantics directly to a Boolean bad region."""
    positions = {name: i for i, (name, _) in enumerate(policy["state"])}
    old = {name: bool((state >> i) & 1) for name, i in positions.items()}
    members = set(map(tuple, policy["members"]))
    levels = {alias["name"]: i for i, alias in enumerate(policy["aliases"])}

    def atom(value):
        work.charge(category="symbolic_guard_atoms")
        field = value["field"]
        if field == "state":
            return diagram.constant(old[value["name"]] == value["value"])
        def truth(name):
            equal = ((request[0], name) in members) if field == "role" else request[{"principal": 0, "resource": 1, "action": 2}[field]] == name
            return equal != value["negated"]
        if "name" in value:
            return diagram.constant(truth(value["name"]))
        level = levels[value["alias"]]
        return diagram.choice(level, [diagram.constant(truth(name))
                                     for name in policy["aliases"][level]["candidates"]])

    answer = diagram.constant(("deny", state) != expected)
    for rule in reversed(policy["rules"]):
        guard = diagram.true
        for value in rule["guard"]:
            guard = diagram.ite(guard, atom(value), diagram.false)
            if guard == diagram.false:
                break
        if guard == diagram.false:
            continue
        post = dict(old)
        for effect in rule["updates"]:
            post[effect["name"]] = effect["value"] if "value" in effect else old[effect["from"]] != effect["negated"]
        following = sum(int(post[name]) << i for name, i in positions.items())
        answer = diagram.ite(guard, diagram.constant((rule["decision"], following) != expected), answer)
    return answer


def symbolic_family_profile(
    policy: dict[str, Any], machine: dict[str, Any],
    family: Iterable[dict[str, str]] | None = None,
    protocol: dict[str, Any] | None = None,
    *, backend: str = "finite-domain", budget: int = DEFAULT_WORK_BUDGET,
    family_limit: int = DEFAULT_FAMILY_LIMIT, node_limit: int = 100_000,
    operation_limit: int = 2_000_000,
) -> dict[str, Any]:
    """Return all legal bindings with the same canonical shortest full replays.

    Validation, family encoding, complete graph admission, symbolic predicates,
    output materialization and fixed-binding replays are part of this call.
    Both work envelopes are enforced during construction; neither exhaustion
    nor an incomplete admitted graph returns a partial family.
    """
    inspect_policy(policy)
    ensure(backend in ("finite-domain", "cudd"), "unknown symbolic backend")
    ensure(type(node_limit) is int and node_limit >= 2, "symbolic node limit", "inconclusive")
    ensure(type(operation_limit) is int and operation_limit >= 0,
           "symbolic operation limit", "inconclusive")
    with_protocol = protocol is not None
    if with_protocol:
        _inspect_partial_interface(policy, machine, protocol)
    else:
        inspect_machine(policy, machine, compare_initial=False)
        protocol = {"initial": 0, "transitions": [[0] * len(machine["alphabet"])]}
    work = _WorkBudget(budget)
    bindings = _normalize_family(policy, family, work, family_limit)
    source_initial = sum(int(value) << i for i, (_, value) in enumerate(policy["state"]))
    initial_bad = source_initial != machine["observations"][machine["initial"]]
    profiles = [None] * len(bindings)
    symbolic = {"backend": backend, "nodes": 0, "conditional_operations": 0,
                "predicate_constructions": 0, "predicate_cache_hits": 0,
                "first_bad_regions": 0, "alias_order": [a["name"] for a in policy["aliases"]]}
    if initial_bad:
        graph = {"graph_traversals": 0, "target_protocol_reachable_states": None,
                 "target_reachable_states": None, "graph_cells_inspected": 0,
                 "graph_enabled_edges": 0, "protocol_disabled_cells": 0,
                 "protocol_excluded_missing_cells": 0}
        for index, binding in enumerate(bindings):
            work.charge(category="output_rows")
            profiles[index] = {"binding": binding, "equivalent": False, "length": 0,
                               "indices": [], "trace": [], "reason": "initial observation"}
    else:
        parents, cells, graph = _reachable_product(machine, protocol, work)
        diagram = (_FiniteDiagram if backend == "finite-domain" else _CuddDiagram)(
            policy["aliases"], node_limit, operation_limit)
        axes = [a["name"] for a in policy["aliases"]]
        lookups = [{name: i for i, name in enumerate(a["candidates"])} for a in policy["aliases"]]
        assignments = [tuple(lookup[binding[name]] for name, lookup in zip(axes, lookups))
                       for binding in bindings]
        indices_by_assignment = {values: i for i, values in enumerate(assignments)}
        active = diagram.domain() if family is None else _family_relation(diagram, assignments, work)
        cache, partitions = {}, []
        for q, t, index in cells:
            if active == diagram.false:
                break
            work.charge(category="symbolic_cells")
            state = machine["observations"][q]
            request = machine["alphabet"][index]
            edge = machine["transitions"][q][index]
            expected = (edge[0], machine["observations"][edge[1]])
            key = (state, tuple(request), expected)
            if key not in cache:
                cache[key] = _mismatch(diagram, policy, state, request, expected, work)
            else:
                symbolic["predicate_cache_hits"] += 1
            bad = cache[key]
            fresh = diagram.ite(active, bad, diagram.false)
            if fresh != diagram.false:
                partitions.append((fresh, q, t, index, _indices_to(parents, (q, t)) + [index]))
                active = diagram.ite(bad, diagram.false, active)
        for region, q, t, index, word in partitions:
            for assignment in diagram.assignments(region):
                work.charge(category="symbolic_materialized_members")
                ensure(assignment in indices_by_assignment, "symbolic output contains an illegal binding")
                member = indices_by_assignment[assignment]
                ensure(profiles[member] is None, "symbolic first-failure regions overlap")
                binding = bindings[member]
                trace = (_replay(policy, machine, protocol, binding, word, work)
                         if with_protocol else _reference_replay(policy, machine, word,
                                                               [binding] * len(word), work=work))
                ensure(trace and all(row["compared_equal"] for row in trace[:-1])
                       and not trace[-1]["compared_equal"], "symbolic fixed-binding shortest replay")
                work.charge(category="output_rows")
                result = {"binding": binding, "equivalent": False, "length": len(word),
                          "indices": word, "trace": trace}
                if with_protocol:
                    result.update(target_state=q, protocol_state=t, request=index)
                profiles[member] = result
        for index, binding in enumerate(bindings):
            if profiles[index] is None:
                work.charge(category="output_rows")
                profiles[index] = {"binding": binding, "equivalent": True, "length": None,
                                   "indices": None, "trace": None}
        symbolic.update(diagram.metrics(), predicate_constructions=len(cache),
                        first_bad_regions=len(partitions))
    matching = [row["binding"] for row in profiles if row["equivalent"]]
    failing = [row for row in profiles if not row["equivalent"]]
    strata = {}
    for row in profiles:
        key = "infinity" if row["equivalent"] else str(row["length"])
        strata[key] = strata.get(key, 0) + 1
    return {"status": "equivalent" if not failing else "mismatch", "accepted": not failing,
            "classification": "all" if not failing else "none" if not matching else "some",
            "bindings": len(profiles), "matching_bindings": len(matching),
            "failing_bindings": len(failing), "matching_family": matching,
            "shortest_failure": min(row["length"] for row in failing) if failing else None,
            "strata": strata, "profiles": profiles, **graph, "symbolic": symbolic,
            "transition_evaluations": 0, "replay_evaluations": work.categories.get("replay_steps", 0),
            **work.report(),
            "scope": "complete legal fixed-binding family with decision-diagram partitions"}
