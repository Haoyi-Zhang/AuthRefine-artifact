"""Independent initial-store equations and fixed-binding history comparison.

No native collector, production checker, strategy constructor, or finite-audit
module is imported. Row identifiers here are one-based. Every candidate is a
single row-to-credential permutation for the complete history, including all
fixture reconstruction events.
"""
from itertools import permutations

from .io import fields, integer, require, same


def family(size):
    return [list(beta) for beta in permutations(range(1, size + 1))]


def rows(size, state):
    return [{"id": i, "token": f"authrefine-owned-session-{i}", "user_id": 101,
             "expiry_date": "2020-01-01T00:01:00", "max_expiry_date": "2020-01-01T00:02:00"}
            for i in range(1, size + 1) if state & (1 << (i - 1))]


def validate_operation(operation, size, kind):
    require(type(operation) is dict and type(operation.get("action")) is str,
            "operation: action string required")
    action = operation["action"]
    if action in ("lookup", "remove"):
        fields(operation, ("action", "row"), "request operation")
        integer(operation["row"], "request row", 1, size)
    else:
        fields(operation, ("action",), "reconstruction operation")
        allowed = "restore_complete" if kind == "optimal" else "reset_initial"
        require(action == allowed, "reconstruction outside declared caller")


def step(binding, state, operation):
    """Decision, successor store, and selected row; no physical implementation."""
    action, row = operation["action"], operation["row"]
    if action == "remove":
        return "allow", state & ~(1 << (row - 1)), None
    selected = next((i for i, credential in enumerate(binding, 1)
                     if credential == row and state & (1 << (i - 1))), None)
    return ("allow" if selected is not None else "deny"), state, selected


def optimum(size, initial, observation):
    absent = size - initial.bit_count()
    return {"requests": (size - 1 if observation == "selected-row" else
                         2 * (size - 1) - int(0 < absent < size)),
            "restore_complete": int(absent >= 2), "reset_initial": 0}


def expected_observation(size, state, operation):
    """All retained native fields, independently calculated for identity."""
    action, row = operation["action"], operation["row"]
    before = rows(size, state)
    following = state & ~(1 << (row - 1)) if action == "remove" else state
    after = rows(size, following)
    selected = next((value for value in before if value["id"] == row), None) if action == "lookup" else None
    allowed = action == "remove" or selected is not None
    resource = f"{'credential' if action == 'lookup' else 'row'}-{row}"
    return {"request": ["client", resource, action], "token_argument": f"authrefine-owned-session-{row}",
            "returned_user_id": 101 if selected is not None else None,
            "selected_record": None if selected is None else {key: selected[key] for key in ("id", "token", "user_id")},
            "decision": "allow" if allowed else "deny", "before_state": state,
            "after_state": following, "before_rows": before, "after_rows": after,
            "removed_ids": [row] if action == "remove" and state & (1 << (row - 1)) else [],
            "store_changed": state != following}


def validate_trace(case, trace):
    fields(trace, ("id", "initial_state", "initial_rows", "events", "final_state", "final_rows"), "native trace")
    size, initial = case["size"], case["initial"]
    require(type(trace["id"]) is str and trace["id"] == case["id"], "native case identity differs")
    require(same(trace["initial_state"], initial) and same(trace["initial_rows"], rows(size, initial)),
            "native initial physical rows differ")
    require(type(trace["events"]) is list and len(trace["events"]) == len(case["word"]),
            "native event count differs from declared word")
    state = initial
    counts = {"requests": 0, "restore_complete": 0, "reset_initial": 0}
    for operation, event in zip(case["word"], trace["events"]):
        validate_operation(operation, size, case["kind"])
        action = operation["action"]
        if action in ("lookup", "remove"):
            fields(event, ("action", "row", "observation"), "native request event")
            require(same({"action": event["action"], "row": event["row"]}, operation),
                    "native action differs from declared word")
            expected = expected_observation(size, state, operation)
            require(same(event["observation"], expected), "native request/physical rows/selected record differs")
            state = expected["after_state"]
            counts["requests"] += 1
        else:
            fields(event, ("action", "before_state", "before_rows", "after_state", "after_rows"), "fixture reconstruction")
            following = (1 << size) - 1 if action == "restore_complete" else initial
            expected = {"action": action, "before_state": state, "before_rows": rows(size, state),
                        "after_state": following, "after_rows": rows(size, following)}
            require(same(event, expected), "fixture reconstruction changed rows, history, or restoration semantics")
            state = following
            counts[action] += 1
    require(same(trace["final_state"], state) and same(trace["final_rows"], rows(size, state)),
            "native final physical rows differ")
    return counts


def compare_history(case, trace, binding):
    """Return first disagreement; evaluate the entire recorded history anyway."""
    state = case["initial"]
    first = None
    comparisons = 0
    for index, (operation, event) in enumerate(zip(case["word"], trace["events"])):
        action = operation["action"]
        if action in ("restore_complete", "reset_initial"):
            state = (1 << case["size"]) - 1 if action == "restore_complete" else case["initial"]
            # Neither binding nor the earlier comparison is reset.
            continue
        decision, following, selected = step(binding, state, operation)
        observed = event["observation"]
        agrees = decision == observed["decision"] and following == observed["after_state"]
        if case["observation"] == "selected-row":
            record = observed["selected_record"]
            agrees = agrees and selected == (None if record is None else record["id"])
        if not agrees and first is None:
            first = index
        state = following
        comparisons += 1
    return first, comparisons


def certify(case, trace):
    counts = validate_trace(case, trace)
    bindings = family(case["size"])
    first, comparisons = [], 0
    for binding in bindings:
        mismatch, checked = compare_history(case, trace, binding)
        first.append(mismatch)
        comparisons += checked
    survivors = [binding for binding, mismatch in zip(bindings, first) if mismatch is None]
    identity = list(range(1, case["size"] + 1))
    if case["kind"] == "optimal":
        require(survivors == [identity], "optimal native strategy does not uniquely certify identity")
        require(counts == optimum(case["size"], case["initial"], case["observation"]),
                "native optimal request/restoration counts differ from theorem")
    else:
        absent = [i for i in identity if not case["initial"] & (1 << (i - 1))]
        require(len(absent) == 2 and counts["restore_complete"] == 0 and counts["reset_initial"] == 2,
                "reset control must preserve two absent rows over two resets")
        alternate = list(identity)
        a, b = absent
        alternate[a - 1], alternate[b - 1] = alternate[b - 1], alternate[a - 1]
        require(survivors == sorted([identity, alternate]), "reset-initial control has the wrong exact surviving family")
    return {"id": case["id"], "size": case["size"], "initial": case["initial"],
            "observation": case["observation"], "kind": case["kind"], "counts": counts,
            "tested_bindings": len(bindings), "request_comparisons": comparisons,
            "surviving_bindings": survivors, "first_disagreement_by_binding": first,
            "initial_state": trace["initial_state"], "final_state": trace["final_state"]}
