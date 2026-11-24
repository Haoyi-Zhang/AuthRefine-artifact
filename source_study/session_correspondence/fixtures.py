"""Owned session fixtures and independently supplied correspondence contracts.

Increasing the number of rows changes the experiment's input, not either
upstream method. The family contains bijections; unrelated Cartesian
combinations are not silently added to it.
"""
from datetime import timedelta
from itertools import permutations, product

from source_study.stateful_sequence.fixtures import NOW, USER, serialized_rows


def require_size(size):
    if type(size) is not int or not 2 <= size <= 6:
        raise ValueError("session count must be an integer in 2..6")


def credentials(size):
    require_size(size)
    return [f"credential-{i}" for i in range(1, size + 1)]


def aliases(size):
    require_size(size)
    return [f"credential-for-row-{i}" for i in range(1, size + 1)]


def rows(size):
    require_size(size)
    return [{"id": i, "token": f"authrefine-owned-session-{i}", "user_id": USER,
             "expiry_date": NOW + timedelta(seconds=60),
             "max_expiry_date": NOW + timedelta(seconds=120)}
            for i in range(1, size + 1)]


def alphabet(size):
    resources = sorted(credentials(size) + ["missing"] +
                       [f"row-{i}" for i in range(1, size + 1)])
    return [["client", resource, action] for resource, action in
            product(resources, ("lookup", "remove"))]


def token_for(size, request):
    if request not in alphabet(size):
        raise ValueError("request outside declared multi-session interface")
    _, resource, action = request
    prefix = "credential-" if action == "lookup" else "row-"
    return (f"authrefine-owned-session-{resource[len(prefix):]}"
            if resource.startswith(prefix) else "authrefine-owned-missing-session")


def family(size):
    return [dict(zip(aliases(size), permutation))
            for permutation in permutations(credentials(size))]


def contract(size):
    # Import only when the driver has already frozen native acquisition.
    from language import normalize
    states = [f"session-{i}-present" for i in range(1, size + 1)]
    def named(field, name):
        return {"field": field, "name": name, "negated": False}
    rules = [{"decision": "allow", "guard": [named("action", "remove"),
               named("resource", f"row-{i}")],
              "updates": [{"name": states[i - 1], "value": False}]}
             for i in range(1, size + 1)]
    rules.append({"decision": "allow", "guard": [named("action", "remove")], "updates": []})
    rules.extend({"decision": "allow", "guard": [named("action", "lookup"),
                  {"field": "resource", "alias": name, "negated": False},
                  {"field": "state", "name": states[i], "value": True}], "updates": []}
                 for i, name in enumerate(aliases(size)))
    return normalize({"principals": ["client"],
                      "resources": sorted({request[1] for request in alphabet(size)}),
                      "actions": ["lookup", "remove"], "roles": [], "members": [],
                      "state": [[name, True] for name in states],
                      "aliases": [{"name": name, "kind": "resource", "candidates": credentials(size)}
                                  for name in aliases(size)], "rules": rules})


def callers(requests):
    return {
        "unrestricted": {"initial": 0, "transitions": [[0] * len(requests)]},
        "lookup-only": {"initial": 0, "transitions": [
            [0 if request[2] == "lookup" else None for request in requests]]},
        "one-removal": {"initial": 0, "transitions": [
            [1 if request[2] == "remove" else 0 for request in requests],
            [None if request[2] == "remove" else 1 for request in requests]]},
    }


def document(size):
    return {"sessions": size, "clock": NOW.isoformat(),
            "initial_rows": serialized_rows(rows(size)), "alphabet": alphabet(size),
            "candidate_family": family(size), "callers": callers(alphabet(size)),
            "observation": "returned authorization decision and presence of each identified store row",
            "richer_observation": "the same record plus the selected row identity on lookup",
            "shared_user": USER,
            "input_design": "All bijections between presented credential labels and independently identified store rows.",
            "source_change": "The baseline executes the unmodified selected source methods. The omitted-delete arm is an introduced control."}
