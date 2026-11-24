"""Independent set equations and target/reference/caller BFS.

No production policy evaluator, support analysis, native collector, source
lowerer or profile implementation is imported here.
"""
from collections import deque
from source_study.native_policy_store.fixtures import ROWS, aliases, alphabet, initial_state, resources


def step(state, request, binding, *, durable=True):
    count = len(ROWS)
    disk, memory = state & ((1 << count) - 1), state >> count
    action = request[2]
    if action == "restart":
        return "allow", disk | (disk << count)
    selected = [i for i, name in enumerate(aliases()) if binding[name] == request[1]]
    if len(selected) != 1:
        raise ValueError("fixed correspondence is not a complete row bijection")
    bit = 1 << selected[0]
    present = bool(memory & bit)
    result = not present if action == "add" else present
    if action not in ("add", "authorize", "remove"):
        raise ValueError("unknown store operation")
    if result and action != "authorize":
        memory = memory | bit if action == "add" else memory & ~bit
        if durable:
            disk = memory
    return ("allow" if result else "deny"), disk | (memory << count)


def replay(mask, machine, binding, word, protocol=None, *, observe_state=True):
    caller = protocol or {"initial": 0, "transitions": [[0] * len(machine["alphabet"])]}
    source, target, call = initial_state(mask), machine["initial"], caller["initial"]
    rows = []
    for index in word:
        request = machine["alphabet"][index]
        next_call = caller["transitions"][call][index]
        if next_call is None:
            raise ValueError("witness enters a disabled caller cell")
        decision, successor = machine["transitions"][target][index]
        actual = step(source, request, binding)
        expected = decision, machine["observations"][successor]
        row = {"request": list(request), "binding": dict(binding),
               "source": list(actual), "target": list(expected),
               "decision_equal": actual[0] == expected[0], "state_equal": actual[1] == expected[1],
               "compared_equal": actual[0] == expected[0] and (not observe_state or actual[1] == expected[1])}
        if protocol is not None:
            row.update(source_state=source, target_state=target, protocol_state=call)
        rows.append(row)
        source, target, call = actual[1], successor, next_call
    return rows


def profile(mask, machine, binding, protocol=None, *, observe_state=True):
    caller = protocol or {"initial": 0, "transitions": [[0] * len(machine["alphabet"])]}
    first = initial_state(mask), machine["initial"], caller["initial"]
    if observe_state and first[0] != machine["observations"][first[1]]:
        return {"binding": binding, "equivalent": False, "length": 0, "indices": [], "trace": []}
    paths, todo = {first: []}, deque([first])
    while todo:
        reference, target, call = current = todo.popleft()
        for index, request in enumerate(machine["alphabet"]):
            next_call = caller["transitions"][call][index]
            if next_call is None:
                continue
            decision, successor = machine["transitions"][target][index]
            expected, following = step(reference, request, binding)
            word = paths[current] + [index]
            if expected != decision or (observe_state and following != machine["observations"][successor]):
                return {"binding": binding, "equivalent": False, "length": len(word), "indices": word,
                        "trace": replay(mask, machine, binding, word, protocol, observe_state=observe_state)}
            node = following, successor, next_call
            if node not in paths:
                paths[node] = word
                todo.append(node)
    return {"binding": binding, "equivalent": True, "length": None, "indices": None, "trace": None}


def check_native_witness(mask, binding, word, observations, *, observe_state=True):
    requests = alphabet()
    if (type(binding) is not dict or set(binding) != set(aliases())
            or any(type(value) is not str for value in binding.values())
            or set(binding.values()) != set(resources())):
        raise ValueError("native witness requires a legal fixed correspondence")
    if (not isinstance(word, (list, tuple)) or not isinstance(observations, (list, tuple))
            or len(word) != len(observations)):
        raise ValueError("native witness record count differs")
    if any(type(index) is not int or not 0 <= index < len(requests) for index in word):
        raise ValueError("native witness index is outside the declared alphabet")
    state, target, previous, agreement = initial_state(mask), initial_state(mask), None, []
    for index, observed in zip(word, observations):
        if not isinstance(observed, dict) or observed.get("request") != requests[index]:
            raise ValueError("native witness request differs from its declared index")
        before, after = observed.get("before"), observed.get("after")
        if (not isinstance(before, dict) or not isinstance(after, dict)
                or type(before.get("state")) is not int or type(after.get("state")) is not int
                or not 0 <= before["state"] < (1 << (2 * len(ROWS)))
                or not 0 <= after["state"] < (1 << (2 * len(ROWS)))):
            raise ValueError("native witness store observation is malformed")
        if before["state"] != target or (previous is not None and before != previous):
            raise ValueError("native witness does not carry the preceding complete store")
        if observed.get("decision") not in ("allow", "deny"):
            raise ValueError("native witness has no declared interface outcome")
        decision, state = step(state, requests[index], binding)
        agreement.append(decision == observed["decision"] and
                         (not observe_state or state == after["state"]))
        target, previous = after["state"], after
    if not agreement or not all(agreement[:-1]) or agreement[-1]:
        raise ValueError("native witness does not first disagree at its last request")
    return len(agreement)
