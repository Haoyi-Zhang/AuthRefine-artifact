"""Direct contract equations and an independent product search.

No production evaluator, compiler, support function, profile traversal or replay
routine is imported. A concrete binding is never changed within a trace.
"""
from collections import deque


def step(size, state, request, binding):
    _, resource, action = request
    if action == "remove":
        for row in range(1, size + 1):
            if resource == f"row-{row}":
                state &= ~(1 << (row - 1))
        return "allow", state
    selected = [row for row in range(1, size + 1)
                if state & (1 << (row - 1)) and
                resource == binding[f"credential-for-row-{row}"]]
    return ("allow" if selected else "deny"), state


def selected_row(size, state, request, binding):
    if request[2] != "lookup":
        return None
    return next((row for row in range(1, size + 1)
                 if state & (1 << (row - 1)) and
                 request[1] == binding[f"credential-for-row-{row}"]), None)


def profile(size, machine, binding, protocol=None, selected=None):
    caller = protocol or {"initial": 0, "transitions": [[0] * len(machine["alphabet"])]}
    first = ((1 << size) - 1, machine["initial"], caller["initial"])
    if first[0] != machine["observations"][first[1]]:
        return {"binding": binding, "equivalent": False, "length": 0, "indices": [], "trace": []}
    paths, waiting = {first: []}, deque([first])
    while waiting:
        reference, target, call = current = waiting.popleft()
        for index, request in enumerate(machine["alphabet"]):
            next_call = caller["transitions"][call][index]
            if next_call is None:
                continue
            target_decision, next_target = machine["transitions"][target][index]
            reference_decision, next_reference = step(size, reference, request, binding)
            different = (reference_decision, next_reference) != (
                target_decision, machine["observations"][next_target])
            if selected is not None and request[2] == "lookup":
                different = different or selected_row(size, reference, request, binding) != selected[(target, index)]
            word = paths[current] + [index]
            if different:
                trace = replay(size, machine, binding, word, protocol, selected)
                if not trace or any(not row["compared_equal"] for row in trace[:-1]) or trace[-1]["compared_equal"]:
                    raise ValueError("independent profile does not first disagree in its complete replay")
                return {"binding": binding, "equivalent": False, "length": len(word),
                        "indices": word, "trace": trace}
            following = (next_reference, next_target, next_call)
            if following not in paths:
                paths[following] = word
                waiting.append(following)
    return {"binding": binding, "equivalent": True, "length": None, "indices": None, "trace": None}


def replay(size, machine, binding, word, protocol=None, selected=None):
    caller = protocol or {"initial": 0, "transitions": [[0] * len(machine["alphabet"])]}
    source, target, call = (1 << size) - 1, machine["initial"], caller["initial"]
    result = []
    for index in word:
        request = machine["alphabet"][index]
        next_call = caller["transitions"][call][index]
        if next_call is None:
            raise ValueError("independent replay entered a disabled caller cell")
        decision, successor = machine["transitions"][target][index]
        actual = step(size, source, request, binding)
        expected = (decision, machine["observations"][successor])
        row = {"request": list(request), "binding": dict(binding),
               "source": list(actual), "target": list(expected),
               "decision_equal": actual[0] == expected[0], "state_equal": actual[1] == expected[1],
               "compared_equal": actual == expected}
        if selected is not None:
            reference_identity = selected_row(size, source, request, binding)
            observed_identity = selected[(target, index)] if request[2] == "lookup" else None
            identity_equal = reference_identity == observed_identity
            row.update(reference_selected_row=reference_identity, observed_selected_row=observed_identity,
                       identity_equal=identity_equal, compared_equal=actual == expected and identity_equal)
        if protocol is not None:
            row.update(source_state=source, target_state=target, protocol_state=call)
        result.append(row)
        source, target, call = actual[1], successor, next_call
    return result


def check_native_witness(size, binding, indices, observations, *, selected_identity=False):
    """Validate the declared word against its records and fixed interpretation.

The established decision/presence callers can supply projected records with
request, decision and after_state. Full native records additionally have their
before states checked for continuity. Identity-aware checks require the actual
selected_record field. The declared request word is checked in both modes.
    """
    if len(indices) != len(observations):
        raise ValueError("native witness record count differs")
    resources = sorted([f"credential-{row}" for row in range(1, size + 1)] + ["missing"] +
                       [f"row-{row}" for row in range(1, size + 1)])
    alphabet = [["client", resource, action] for resource in resources for action in ("lookup", "remove")]
    reference = (1 << size) - 1
    target = reference
    comparisons = []
    for index, observed in zip(indices, observations):
        if type(index) is not int or not 0 <= index < len(alphabet):
            raise ValueError("native witness request index is outside the declared alphabet")
        request = alphabet[index]
        if observed["request"] != request:
            raise ValueError("native witness request differs from its declared word")
        if "before_state" in observed and observed["before_state"] != target:
            raise ValueError("native witness state continuity differs")
        if type(observed["after_state"]) is not int or not 0 <= observed["after_state"] < (1 << size):
            raise ValueError("native witness has an invalid observed state")
        expected_identity = selected_row(size, reference, request, binding)
        decision, reference = step(size, reference, request, binding)
        agrees = (decision, reference) == (observed["decision"], observed["after_state"])
        if selected_identity:
            if "selected_record" not in observed:
                raise ValueError("identity-aware native witness has no selected-record observation")
            selected = observed["selected_record"]
            observed_identity = None if selected is None else selected["id"]
            if request[2] != "lookup" and selected is not None:
                raise ValueError("removal has an unexpected selected-record observation")
            agrees = agrees and expected_identity == observed_identity
        comparisons.append(agrees)
        target = observed["after_state"]
    if not comparisons or not all(comparisons[:-1]) or comparisons[-1]:
        raise ValueError("native record does not first disagree at the selected final request")
    return len(comparisons)
