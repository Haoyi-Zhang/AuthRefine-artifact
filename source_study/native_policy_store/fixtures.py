"""Supplied row correspondences and a durable-store reference contract.

These rows are the existing Conet study inputs. A review correspondence is a
single bijection shared by add, remove and authorize; it is not a discovered
ambiguity in an upstream installation.
"""
from itertools import permutations, product

ROWS = (("finance", "invoice.verify", "invoke"),
        ("marketing", "research.find_leads", "invoke"),
        ("marketing", "invoice.verify", "invoke"))
ARMS = ("original", "repaired")
CALLERS = ("unrestricted", "query-only", "one-mutation", "mutation-restart-query")
TOTAL_METHODS = ("per-binding-product", "per-binding-target", "shared-target", "support-indexed")
METHODS = TOTAL_METHODS + tuple(f"protocol-{algorithm}/{caller}"
    for caller in CALLERS for algorithm in ("scan", "grouped"))


def resources():
    return [f"row-{i}" for i in range(1, len(ROWS) + 1)]


def aliases():
    return [f"request-for-slot-{i}" for i in range(1, len(ROWS) + 1)]


def state_names():
    return [f"{layer}-{i}" for layer in ("disk", "memory") for i in range(1, len(ROWS) + 1)]


def alphabet():
    return [["api", label, action] for label, action in product(
        resources(), ("add", "authorize", "remove", "restart"))]


def family():
    return [dict(zip(aliases(), values)) for values in permutations(resources())]


def initial_state(mask):
    if type(mask) is not int or not 0 <= mask < (1 << len(ROWS)):
        raise ValueError("initial policy must be a subset of the three declared rows")
    return mask | (mask << len(ROWS))


def contract(mask):
    from language import normalize
    def named(field, name):
        return {"field": field, "name": name, "negated": False}
    rules = []
    for i, alias in enumerate(aliases(), 1):
        for action in ("add", "authorize", "remove"):
            updates = []
            if action != "authorize":
                updates = [{"name": f"memory-{i}", "value": action == "add"}]
                updates += [{"name": f"disk-{j}", "value": action == "add"} if i == j else
                            {"name": f"disk-{j}", "from": f"memory-{j}", "negated": False}
                            for j in range(1, len(ROWS) + 1)]
            rules.append({"decision": "allow", "guard": [named("action", action),
                {"field": "resource", "alias": alias, "negated": False},
                {"field": "state", "name": f"memory-{i}", "value": action != "add"}],
                "updates": updates})
    rules.append({"decision": "allow", "guard": [named("action", "restart")],
                  "updates": [{"name": f"memory-{i}", "from": f"disk-{i}", "negated": False}
                              for i in range(1, len(ROWS) + 1)]})
    state = initial_state(mask)
    return normalize({"principals": ["api"], "resources": resources(),
        "actions": ["add", "authorize", "remove", "restart"], "roles": [], "members": [],
        "state": [[name, bool(state & (1 << i))] for i, name in enumerate(state_names())],
        "aliases": [{"name": alias, "kind": "resource", "candidates": resources()} for alias in aliases()],
        "rules": rules})


def callers():
    requests = alphabet()
    mutating = lambda request: request[2] in ("add", "remove")
    return {
        "unrestricted": {"initial": 0, "transitions": [[0] * len(requests)]},
        "query-only": {"initial": 0, "transitions": [[0 if r[2] == "authorize" else None for r in requests]]},
        "one-mutation": {"initial": 0, "transitions": [
            [1 if mutating(r) else 0 for r in requests],
            [None if mutating(r) else 1 for r in requests]]},
        "mutation-restart-query": {"initial": 0, "transitions": [
            [1 if mutating(r) else None for r in requests],
            [2 if r[2] == "restart" else None for r in requests],
            [2 if r[2] == "authorize" else None for r in requests]]},
    }


def document():
    return {"application": "Conet", "rows": [list(row) for row in ROWS],
        "row_origin": "The three owned ACL rows already supplied to source_study/repair_profiles.py.",
        "initial_policy_masks": list(range(8)), "arms": list(ARMS), "alphabet": alphabet(),
        "family": family(), "callers": callers(),
        "family_origin": "Six review hypotheses pairing reference row slots with request tuples; the same bijection is fixed across add/remove/authorize and the entire history.",
        "observation": "Boolean API return plus exact identified policy rows in the current instance and on disk.",
        "restart": "Construct a fresh original PolicyEngine instance using the same owned policy file.",
        "restart_result": "Successful instance construction is encoded as an allowed interface event; the actual native result type is recorded separately.",
        "reference": "Successful set mutations persist the complete new set; restart loads that set.",
        "scope": "Complete selected PolicyEngine module import and method execution, native Casbin FileAdapter and owned files; no service deployment or administrative-access claim."}
