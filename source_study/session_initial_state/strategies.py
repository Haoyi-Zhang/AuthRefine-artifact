"""Predeclared request words; no observation or reference evaluator is used."""


OBSERVATIONS = ("projected", "selected-row")


def validate_context(size, initial, observation):
    if type(size) is not int or not 2 <= size <= 6:
        raise ValueError("session count must be an integer in 2..6")
    if type(initial) is not int or not 0 <= initial < (1 << size):
        raise ValueError("initial store must be a valid integer mask")
    if type(observation) is not str or observation not in OBSERVATIONS:
        raise ValueError("unknown observation contract")


def request(action, row):
    return {"action": action, "row": row}


def optimal(size, initial, observation):
    validate_context(size, initial, observation)
    present = [i for i in range(1, size + 1) if initial & (1 << (i - 1))]
    absent = [i for i in range(1, size + 1) if not initial & (1 << (i - 1))]
    if observation == "selected-row":
        if len(absent) >= 2:
            return [{"action": "restore_complete"}] + [request("lookup", i) for i in range(1, size)]
        return [request("lookup", i) for i in present[:size - 1]]
    if not absent:
        return [request(action, i) for i in range(1, size) for action in ("remove", "lookup")]
    if not present:
        return [{"action": "restore_complete"}] + [
            request(action, i) for i in range(1, size) for action in ("remove", "lookup")]
    word = [request("lookup", absent[-1])]
    word += [request(action, i) for i in present[:-1] for action in ("remove", "lookup")]
    if len(absent) >= 2:
        word += [{"action": "restore_complete"}]
        word += [request(action, i) for i in absent[:-1] for action in ("remove", "lookup")]
    return word


def reset_control(size, observation):
    """Keep exactly two rows absent across two actual reset-to-initial events."""
    initial = (1 << (size - 2)) - 1
    validate_context(size, initial, observation)
    present = list(range(1, size - 1))
    absent = [size - 1, size]
    word = [request("lookup", i) for i in range(1, size + 1)]
    word += [request(action, i) for i in present for action in ("remove", "lookup")]
    word += [{"action": "reset_initial"}]
    word += [request("lookup", i) for i in range(1, size + 1)]
    word += [{"action": "reset_initial"}]
    word += [request(action, i) for i in absent for action in ("remove", "lookup")]
    return initial, word


def cases():
    result = []
    for size in range(2, 7):
        for initial in range(1 << size):
            for observation in OBSERVATIONS:
                result.append({"id": f"n{size}-initial{initial}-{observation}", "size": size,
                               "initial": initial, "observation": observation,
                               "kind": "optimal", "anchors": [],
                               "word": optimal(size, initial, observation)})
        for observation in OBSERVATIONS:
            initial, word = reset_control(size, observation)
            result.append({"id": f"n{size}-reset-initial-{observation}", "size": size,
                           "initial": initial, "observation": observation,
                           "kind": "reset-control", "anchors": [], "word": word})
    return result
