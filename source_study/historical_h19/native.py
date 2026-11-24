"""Execute pinned original modules with native Piccolo, SQLite and Pydantic.

The only subclassed engine method records the already compiled SQL before
delegating unchanged to the native SQLite engine. No application server or
authentication entry is started. Rows and requests are owned finite fixtures.
"""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import tempfile
import types

from .contract import FIELDS, contains_owned_token, normalise
from .source import load_original


def checked_exclusions(table, excluded):
    """Independent native implementation of the owned filter-boundary repair."""
    columns = tuple(table._meta.columns)
    result = list(excluded)
    if any(not any(x is c for c in columns) for x in result):
        raise ValueError("Filter exclusion contains a foreign column")
    for column in columns:
        if type(column._meta.secret) is not bool:
            raise ValueError("Nonboolean secret metadata")
        if column._meta.secret and not any(column is x for x in result):
            result.append(column)
    return tuple(result)


def repaired_crud_class(module):
    original_factory = module.create_pydantic_model

    def factory(table, **kwargs):
        kwargs["exclude_columns"] = checked_exclusions(table, kwargs.get("exclude_columns", ()))
        return original_factory(table, **kwargs)

    original = module.PiccoloCRUD.pydantic_model_filters.fget
    globals_copy = dict(original.__globals__)
    globals_copy["create_pydantic_model"] = factory
    getter = types.FunctionType(original.__code__, globals_copy, original.__name__, original.__defaults__, original.__closure__)
    getter.__kwdefaults__ = original.__kwdefaults__
    return type("OwnedFilterBoundaryRepair", (module.PiccoloCRUD,), {"pydantic_model_filters": property(getter)})


def logged_engine(path: Path):
    from piccolo.engine.sqlite import SQLiteEngine

    class RecordedSQLiteEngine(SQLiteEngine):
        def __init__(self):
            super().__init__(path=str(path))
            self.observations = []

        async def _run_in_new_connection(self, query, args=None, query_type="generic", table=None):
            record = {"sql": query, "args": normalise(args), "query_type": query_type}
            try:
                rows = await super()._run_in_new_connection(query, args=args, query_type=query_type, table=table)
            except Exception as error:
                record.update(outcome="exception", error_type=type(error).__name__, error=str(error))
                self.observations.append(record)
                raise
            record.update(outcome="return", rows=normalise(rows))
            self.observations.append(record)
            return rows

    return RecordedSQLiteEngine()


async def endpoint(crud, engine, params):
    from starlette.requests import Request
    before = len(engine.observations)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    try:
        response = await crud.get_all(request, params=dict(params))
    except Exception as error:
        return {"outcome": "exception", "error_type": type(error).__name__, "error": str(error),
                "sql_calls": engine.observations[before:]}
    body = response.body.decode("utf-8")
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    rows = parsed.get("rows", []) if isinstance(parsed, dict) else []
    return {"outcome": "return", "status": response.status_code, "body": body,
            "json": parsed, "headers": dict(response.headers),
            "row_count": len(rows), "owned_token_value_exposed": contains_owned_token(rows),
            "sql_calls": engine.observations[before:]}


async def low_level_query(table, engine, requested, exclude):
    before = len(engine.observations)
    columns = [getattr(table, field) for field in (FIELDS if requested is None else requested)]
    query = table.select(*columns, exclude_secrets=exclude).order_by(table.id)
    try:
        rows = await query.run()
    except Exception as error:
        result = {"outcome": "exception", "error_type": type(error).__name__, "error": str(error)}
    else:
        result = {"outcome": "return", "rows": normalise(rows), "owned_token_value_exposed": contains_owned_token(rows)}
    # Inspect only after native query compilation. Stringifying a query before
    # executing it can mutate the selected-column delegate and change an empty
    # projection into a later default projection; this observer does neither.
    result["projected_fields"] = [c._meta.name for c in query.columns_delegate.selected_columns]
    result["sql_calls"] = engine.observations[before:]
    return result


async def execute(fixtures: dict) -> dict:
    selections, filters = [], []
    source_transformations = []
    for index, profile in enumerate(fixtures["profiles"]):
        producer, consumer = profile["producer"], profile["consumer"]
        table_module = load_original(producer, "table", f"native_{index}")
        crud_module = load_original(consumer, "crud", f"native_{index}")
        table = table_module.SessionsBase
        crud_type = repaired_crud_class(crud_module) if profile["owned_filter_boundary_repair"] else crud_module.PiccoloCRUD
        source_transformations.append({"profile": profile["id"], "original_module_bytes_modified": False,
                                       "original_function_bodies_modified": False,
                                       "filter_factory_rebound_in_owned_subclass": profile["owned_filter_boundary_repair"]})
        with tempfile.TemporaryDirectory(prefix="authrefine-h19-") as temporary:
            engine = logged_engine(Path(temporary) / "owned.sqlite")
            table._meta._db = engine
            await table.create_table().run()
            for fixture in fixtures["rows"]:
                fields = dict(fixture)
                for key in ("expiry_date", "max_expiry_date"):
                    fields[key] = datetime.fromisoformat(fields[key])
                await table.insert(table(**fields)).run()
            baseline = normalise(await table.select().order_by(table.id).run())
            for context in fixtures["selection_contexts"]:
                override = context["exclude_secrets_override"]
                kwargs = {} if override is None else {"exclude_secrets": override}
                crud = crud_type(table, **kwargs)
                requested = context["requested_fields"]
                params = {} if requested is None else {"__visible_fields": ",".join(requested)}
                query = await low_level_query(table, engine, requested, crud.exclude_secrets)
                response = await endpoint(crud, engine, params)
                selections.append({"profile": profile["id"], "context": context["id"],
                                   "requested_fields": requested, "exclude_secrets_override": override,
                                   "effective_exclusion": crud.exclude_secrets,
                                   "token_metadata_secret": table.token._meta.secret,
                                   "registry_fields": [c._meta.name for c in table._meta.secret_columns],
                                   "filter_fields": list(crud.pydantic_model_filters.model_fields),
                                   "filter_schema": crud.pydantic_model_filters.model_json_schema(),
                                   "visible_fields_options": crud.visible_fields_options,
                                   "query": query, "endpoint": response})
            crud = crud_type(table)
            for context in fixtures["filter_contexts"]:
                filters.append({"profile": profile["id"], "context": context["id"],
                                "params": context["params"],
                                "endpoint": await endpoint(crud, engine, context["params"])})
            after = normalise(await table.select().order_by(table.id).run())
            if baseline != after:
                raise ValueError("Read-only historical comparison changed its fixture store")
            source_transformations[-1]["store_before"] = baseline
            source_transformations[-1]["store_after"] = after
    return {"selection_observations": selections, "filter_observations": filters,
            "execution_scope": source_transformations}
