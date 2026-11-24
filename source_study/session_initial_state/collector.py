"""Execute whole predeclared words against the existing native Sessions table.

Fixture reconstruction is performed by this harness, outside the production
Session API. Each request calls the selected upstream method and native ORM.
No oracle, diagnosis implementation or recorded graph is imported here.
"""
from source_study.session_correspondence.native import Sessions
from source_study.session_correspondence import fixtures
from source_study.stateful_sequence.fixtures import mask, serialized_rows


async def reconstruct(session, state):
    values = [row for row in fixtures.rows(session.size) if state & (1 << (row["id"] - 1))]
    await session.table.delete(force=True).run()
    # An empty initial store is a supported fixture, with no empty INSERT.
    if values:
        await session.table.insert(*[session.table(**row) for row in values]).run()


async def execute(session, case):
    await reconstruct(session, case["initial"])
    initial = await session.snapshot()
    events = []
    for operation in case["word"]:
        action = operation["action"]
        if action in ("lookup", "remove"):
            row = operation["row"]
            resource = f"{'credential' if action == 'lookup' else 'row'}-{row}"
            observed = await session.invoke(["client", resource, action])
            events.append({"action": action, "row": row, "observation": observed})
        else:
            before = await session.snapshot()
            state = (1 << case["size"]) - 1 if action == "restore_complete" else case["initial"]
            await reconstruct(session, state)
            after = await session.snapshot()
            events.append({"action": action, "before_state": mask(before), "before_rows": serialized_rows(before),
                           "after_state": mask(after), "after_rows": serialized_rows(after)})
    final = await session.snapshot()
    return {"id": case["id"], "initial_state": mask(initial), "initial_rows": serialized_rows(initial),
            "events": events, "final_state": mask(final), "final_rows": serialized_rows(final)}


async def acquire(cases, record):
    """Serial source execution, streaming each complete case to its evidence file."""
    source_manifests = []
    for size in range(2, 7):
        session = Sessions(size)
        try:
            await session.initialize()
            source_manifests.append({"size": size, "manifest": session.manifest})
            selected = [case for case in cases if case["size"] == size]
            for case in selected:
                value = await execute(session, case)
                record(value)
            print(f"acquired {len(selected)} complete strategies for {size} rows", flush=True)
        finally:
            session.close()
    return source_manifests
