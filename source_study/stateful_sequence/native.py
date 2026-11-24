"""Native Piccolo 1.16.0 / SQLite execution of the pinned complete module.

This is a serial local fixture run, not a web server or an installed historical
application. Source method bodies, ORM queries and persistence execute normally.
The datetime provider alone is fixed so expiry results are reproducible.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import importlib.metadata
from pathlib import Path
import sys
import tempfile
import types

from . import source
from .fixtures import NOW, rows, serialized_rows, mask, token_for


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            raise ValueError("fixture source uses a naive fixed clock")
        return NOW


class NativeSession:
    def __init__(self, control=None):
        if importlib.metadata.version("piccolo") != "1.16.0":
            raise ValueError("native session replay requires piccolo==1.16.0")
        from piccolo.engine.sqlite import SQLiteEngine
        raw, tree, _, self.manifest = source.load(control)
        self.directory = tempfile.TemporaryDirectory(prefix="authrefine-session-")
        self.module = types.ModuleType("authrefine_owned_sessions_" + (control or "baseline"))
        self.path = str(source.ART / source.SOURCE)
        self.module.__file__ = self.path
        sys.modules[self.module.__name__] = self.module
        # Only the known source file selected and hash-checked above can reach
        # this execution boundary. The original module has ordinary imports and
        # one model class; no source-supplied filename is accepted.
        executable = compile(raw if control is None else tree, self.path, "exec", dont_inherit=True)
        exec(executable, self.module.__dict__)
        self.module.datetime = FixedDateTime
        self.table = self.module.SessionsBase
        self.table._meta._db = SQLiteEngine(path=str(Path(self.directory.name) / "sessions.sqlite"))
        self.control = control

    async def initialize(self):
        await self.table.create_table().run()
        await self.reset()

    async def reset(self, fixture_rows=None):
        values = deepcopy(rows() if fixture_rows is None else fixture_rows)
        await self.table.delete(force=True).run()
        await self.table.insert(*[self.table(**row) for row in values]).run()

    async def snapshot(self):
        fields = [getattr(self.table, key) for key in ("id", "token", "user_id", "expiry_date", "max_expiry_date")]
        return await self.table.select(*fields).order_by(self.table.id).run()

    async def invoke(self, request, increase_seconds=None):
        if request[0] != "client" or request[2] not in ("lookup", "remove"):
            raise ValueError("outside session request interface")
        _, resource, action = request
        token = token_for(resource, action)
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
            if action == "lookup":
                increase = None if increase_seconds is None else timedelta(seconds=increase_seconds)
                result = await self.table.get_user_id(token, increase_expiry=increase)
            else:
                if increase_seconds is not None:
                    raise ValueError("remove has no expiry-increase input")
                result = await self.table.remove_session(token)
        finally:
            sys.settrace(previous)
        after = await self.snapshot()
        if action == "lookup" and len(selected) != 1:
            raise ValueError("native selected-record observation was not reached exactly once")
        return {"request": list(request), "token_argument": token,
                "increase_seconds": increase_seconds, "returned_user_id": result,
                "selected_record": selected[0] if selected else None,
                "decision": "allow" if action == "remove" or result is not None else "deny",
                "before_state": mask(before), "after_state": mask(after),
                "before_rows": serialized_rows(before), "after_rows": serialized_rows(after),
                "removed_ids": sorted(set(row["id"] for row in before) - set(row["id"] for row in after)),
                "store_changed": before != after}

    def close(self):
        sys.modules.pop(self.module.__name__, None)
        self.directory.cleanup()
