"""Independent native and interpreted acquisition of the lifecycle graphs."""
from collections import deque

from .fixtures import alphabet, rows, serialized_rows, mask, expiry_inputs


def lifecycle_invariant(observation):
    current = observation["after_state"]
    expected = [row for row in rows() if current & (1 << (row["id"] - 1))]
    return observation["after_rows"] == serialized_rows(expected)


def machine(graph):
    states = graph["states"]
    indexes = {state: index for index, state in enumerate(states)}
    table = [[None for _ in alphabet()] for _ in states]
    for row in graph["edges"]:
        observation = row["observation"]
        position = indexes[row["from_state"]]
        index = row["input_index"]
        if table[position][index] is not None:
            raise ValueError("duplicate acquired session edge")
        table[position][index] = [observation["decision"], indexes[observation["after_state"]]]
    if any(edge is None for row in table for edge in row):
        raise ValueError("missing acquired session edge")
    return {"state_names": ["session-a-present", "session-b-present"],
            "alphabet": alphabet(), "observations": list(states),
            "initial": indexes[3], "transitions": table}


async def native_graph(session):
    requests = alphabet()
    paths, waiting, edges = {3: []}, deque([3]), []
    prefix_steps = 0
    while waiting:
        state = waiting.popleft()
        prefix = paths[state]
        for index, request in enumerate(requests):
            await session.reset()
            prefix_rows = []
            for earlier in prefix:
                observation = await session.invoke(requests[earlier])
                prefix_steps += 1
                if not lifecycle_invariant(observation):
                    raise ValueError("native prefix leaves admitted lifecycle invariant")
                prefix_rows.append(observation)
            if mask(await session.snapshot()) != state:
                raise ValueError("native prefix did not establish its graph state")
            observation = await session.invoke(request)
            if observation["before_state"] != state or not lifecycle_invariant(observation):
                raise ValueError("native edge leaves admitted lifecycle invariant")
            edges.append({"from_state": state, "input_index": index, "prefix": list(prefix),
                          "prefix_observations": prefix_rows, "observation": observation})
            target = observation["after_state"]
            if target not in paths:
                paths[target] = prefix + [index]
                waiting.append(target)
    graph = {"states": list(paths), "edges": edges, "prefix_steps": prefix_steps,
             "source_operations": len(edges) + prefix_steps}
    graph["machine"] = machine(graph)
    return graph


async def acquire_native():
    # Importing the native arm here does not import production interpreters or
    # any finite checker. The driver freezes this result before comparison.
    from .native import NativeSession
    sessions = []
    try:
        baseline = NativeSession()
        sessions.append(baseline)
        await baseline.initialize()
        good = await native_graph(baseline)
        expired = []
        for fixture in expiry_inputs():
            await baseline.reset(rows(fixture["expiry_a_seconds"], fixture["maximum_a_seconds"]))
            observation = await baseline.invoke(fixture["request"], fixture["increase_seconds"])
            expired.append({"id": fixture["id"], "observation": observation})
        control = NativeSession("omit_delete")
        sessions.append(control)
        await control.initialize()
        bad = await native_graph(control)
        return {"baseline": good, "omit_delete": bad, "expiry_boundaries": expired,
                "source_manifests": [baseline.manifest, control.manifest]}
    finally:
        for session in reversed(sessions):
            session.close()


def interpreted_graph(session):
    requests = alphabet()
    paths, waiting, edges = {3: []}, deque([3]), []
    prefix_steps = 0
    while waiting:
        state = waiting.popleft()
        for index, request in enumerate(requests):
            prefix = paths[state]
            session.reset()
            prefix_rows = []
            for earlier in prefix:
                observed = session.invoke(requests[earlier])
                prefix_steps += 1
                if not lifecycle_invariant(observed):
                    raise ValueError("interpreted prefix leaves admitted lifecycle invariant")
                prefix_rows.append(observed)
            if mask(session.snapshot()) != state:
                raise ValueError("interpreted prefix did not establish its graph state")
            observed = session.invoke(request)
            if observed["before_state"] != state or not lifecycle_invariant(observed):
                raise ValueError("interpreted edge leaves admitted lifecycle invariant")
            edges.append({"from_state": state, "input_index": index, "prefix": list(prefix),
                          "prefix_observations": prefix_rows, "observation": observed})
            following = observed["after_state"]
            if following not in paths:
                paths[following] = prefix + [index]
                waiting.append(following)
    result = {"states": list(paths), "edges": edges, "prefix_steps": prefix_steps,
              "source_operations": len(edges) + prefix_steps}
    result["machine"] = machine(result)
    return result


def acquire_interpreted():
    from .interpreted import InterpretedSession
    baseline, control = InterpretedSession(), InterpretedSession("omit_delete")
    good, bad = interpreted_graph(baseline), interpreted_graph(control)
    expired = []
    for fixture in expiry_inputs():
        baseline.reset(rows(fixture["expiry_a_seconds"], fixture["maximum_a_seconds"]))
        expired.append({"id": fixture["id"], "observation": baseline.invoke(
            fixture["request"], fixture["increase_seconds"])})
    return {"baseline": good, "omit_delete": bad, "expiry_boundaries": expired,
            "source_manifests": [baseline.manifest, control.manifest]}
