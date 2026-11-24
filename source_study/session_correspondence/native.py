"""Acquire complete native graphs without importing a policy evaluator.

Each cell is reached by replaying a recorded prefix from the complete initial
store. It is not initialized from a reference transition table. The selected
upstream module, native ORM and SQLite execute on every operation.
"""
from collections import deque
import sys

from source_study.stateful_sequence.native import NativeSession
from source_study.stateful_sequence.fixtures import mask, serialized_rows
from . import fixtures


class Sessions(NativeSession):
    def __init__(self, size, control=None):
        fixtures.require_size(size)
        self.size = size
        super().__init__(control)

    async def reset(self, fixture_rows=None):
        return await super().reset(fixtures.rows(self.size) if fixture_rows is None else fixture_rows)

    async def invoke(self, request):
        token = fixtures.token_for(self.size, request)
        before = await self.snapshot()
        selected = []
        def trace(frame, event, arg):
            if (frame.f_code.co_filename == self.path and frame.f_code.co_name == "get_user_id"
                    and event == "line" and "session" in frame.f_locals and not selected):
                value = frame.f_locals["session"]
                selected.append(None if value is None else
                                {"id": value.id, "token": value.token, "user_id": value.user_id})
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            if request[2] == "lookup":
                result = await self.table.get_user_id(token, increase_expiry=None)
            else:
                result = await self.table.remove_session(token)
        finally:
            sys.settrace(previous)
        after = await self.snapshot()
        if request[2] == "lookup" and len(selected) != 1:
            raise ValueError("native lookup did not expose exactly one selected-row observation")
        return {"request": list(request), "token_argument": token,
                "returned_user_id": result, "selected_record": selected[0] if selected else None,
                "decision": "allow" if request[2] == "remove" or result is not None else "deny",
                "before_state": mask(before), "after_state": mask(after),
                "before_rows": serialized_rows(before), "after_rows": serialized_rows(after),
                "removed_ids": sorted({r["id"] for r in before} - {r["id"] for r in after}),
                "store_changed": before != after}


def check_store(size, observation):
    expected = serialized_rows([row for row in fixtures.rows(size)
                                if observation["after_state"] & (1 << (row["id"] - 1))])
    if observation["after_rows"] != expected:
        raise ValueError("native operation escaped the declared unexpired-row lifecycle")


async def graph(session):
    size = session.size
    requests = fixtures.alphabet(size)
    initial = (1 << size) - 1
    paths, waiting, edges = {initial: []}, deque([initial]), []
    prefix_operations = 0
    while waiting:
        state = waiting.popleft()
        prefix = paths[state]
        for index, request in enumerate(requests):
            await session.reset()
            prefix_records = []
            for earlier in prefix:
                observed = await session.invoke(requests[earlier])
                check_store(size, observed)
                prefix_records.append(observed)
                prefix_operations += 1
            if mask(await session.snapshot()) != state:
                raise ValueError("native replay prefix did not reach its recorded store")
            observed = await session.invoke(request)
            check_store(size, observed)
            if observed["before_state"] != state:
                raise ValueError("native cell starts from a different store")
            edges.append({"from_state": state, "input_index": index, "prefix": list(prefix),
                          "prefix_observations": prefix_records, "observation": observed})
            following = observed["after_state"]
            if following not in paths:
                paths[following] = prefix + [index]
                waiting.append(following)
    states = list(paths)
    indices = {state: index for index, state in enumerate(states)}
    table = [[None] * len(requests) for _ in states]
    for edge in edges:
        position, index = indices[edge["from_state"]], edge["input_index"]
        if table[position][index] is not None:
            raise ValueError("duplicate native cell")
        observed = edge["observation"]
        table[position][index] = [observed["decision"], indices[observed["after_state"]]]
    if any(cell is None for row in table for cell in row):
        raise ValueError("native graph has an unobserved cell")
    return {"states": states, "edges": edges, "prefix_operations": prefix_operations,
            "source_operations": len(edges) + prefix_operations,
            "machine": {"state_names": [f"session-{i}-present" for i in range(1, size + 1)],
                        "alphabet": requests, "observations": states, "initial": indices[initial],
                        "transitions": table}}


async def acquire(size):
    result = {"sessions": size}
    for label, control in (("baseline", None), ("omit-delete", "omit_delete")):
        session = Sessions(size, control)
        try:
            await session.initialize()
            result[label] = await graph(session)
        finally:
            session.close()
    return result


async def replay_words(size, arm, words):
    """Replay each different physical word once; retain every native record."""
    session = Sessions(size, None if arm == "baseline" else "omit_delete")
    result = []
    try:
        await session.initialize()
        requests = fixtures.alphabet(size)
        for word in sorted(set(tuple(word) for word in words), key=lambda value: (len(value), value)):
            await session.reset()
            observations = []
            for index in word:
                observed = await session.invoke(requests[index])
                check_store(size, observed)
                observations.append(observed)
            result.append({"indices": list(word), "observations": observations})
    finally:
        session.close()
    return result
