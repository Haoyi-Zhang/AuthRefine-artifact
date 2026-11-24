"""Separate in-memory provider for the existing bounded EffectInterpreter.

No native observer, Piccolo query class, SQLite connection or native result is
imported. A small typed adapter represents timestamps as integer seconds and
query-column comparisons as explicit predicates. Selected source bodies stay
complete. These adapters are new source integration work, not frozen transfer.
"""
import ast
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import sys

from .source import load
from .fixtures import NOW, rows, mask, serialized_rows, token_for

ART = Path(__file__).resolve().parents[2]
if str(ART / "src") not in sys.path:
    sys.path.insert(0, str(ART / "src"))
from effect_slice import Capability, DataRecord, EffectInterpreter
from native_casbin import AdmissionError


class SessionInterpreter(EffectInterpreter):
    def value(self, node, env):
        # Python typing.cast is an identity operation. Its first operand is
        # restricted to the two exact non-effectful type expressions used here.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cast":
            types = {"Name(id='datetime', ctx=Load())",
                     "Subscript(value=Name(id='Optional', ctx=Load()), slice=Name(id='int', ctx=Load()), ctx=Load())"}
            if len(node.args) != 2 or node.keywords or ast.dump(node.args[0]) not in types:
                raise AdmissionError("unknown session cast expression")
            self.charge()
            return self.value(node.args[1], env)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            # This rule is restricted syntactically to cls.token == token.
            if (isinstance(node.left, ast.Attribute) and isinstance(node.left.value, ast.Name)
                    and node.left.value.id == "cls" and node.left.attr == "token"):
                left, right = self.value(node.left, env), self.value(node.comparators[0], env)
                if not isinstance(left, DataRecord) or left.kind != "session_token_column" or type(right) is not str:
                    raise AdmissionError("session predicate has wrong operand type")
                self.charge()
                return DataRecord("session_token_predicate", {"token": right})
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            left, right = self.value(node.left, env), self.value(node.right, env)
            if type(left) is not int or type(right) is not int or abs(left) > 86400 or abs(right) > 86400:
                raise AdmissionError("session clock arithmetic outside integer-second fixture domain")
            self.charge()
            return left + right if isinstance(node.op, ast.Add) else left - right
        return super().value(node, env)


class InterpretedSession:
    def __init__(self, control=None):
        _, _, self.program, self.manifest = load(control)
        self.control = control
        self.reset()

    def reset(self, fixture_rows=None):
        self.store = {row["id"]: {**deepcopy(row),
                                  "expiry_date": int((row["expiry_date"] - NOW).total_seconds()),
                                  "max_expiry_date": int((row["max_expiry_date"] - NOW).total_seconds())}
                      for row in (rows() if fixture_rows is None else fixture_rows)}

    def snapshot(self):
        return [{**deepcopy(row), "expiry_date": NOW + timedelta(seconds=row["expiry_date"]),
                 "max_expiry_date": NOW + timedelta(seconds=row["max_expiry_date"])}
                for _, row in sorted(self.store.items())]

    def invoke(self, request, increase_seconds=None):
        if request[0] != "client" or request[2] not in ("lookup", "remove"):
            raise ValueError("outside session request interface")
        _, resource, action = request
        token = token_for(resource, action)
        before = self.snapshot()
        selected = []

        def objects():
            def where(predicate):
                require_predicate(predicate)
                def first():
                    def run():
                        matches = [row for _, row in sorted(self.store.items()) if row["token"] == predicate.fields["token"]]
                        if not matches:
                            selected.append(None)
                            return None
                        original = matches[0]
                        selected.append({key: original[key] for key in ("id", "token", "user_id")})
                        result = DataRecord("session_row", deepcopy(original), frozenset({"expiry_date"}))
                        def save():
                            def apply():
                                self.store[result.fields["id"]]["expiry_date"] = result.fields["expiry_date"]
                                return None
                            return DataRecord("session_save", {"run": Capability("save.run", apply, True)})
                        result.fields["save"] = Capability("row.save", save)
                        return result
                    return DataRecord("session_first", {"run": Capability("query.run", run, True)})
                return DataRecord("session_where", {"first": Capability("query.first", first)})
            return DataRecord("session_objects", {"where": Capability("query.where", where)})

        def require_predicate(predicate):
            if (not isinstance(predicate, DataRecord) or predicate.kind != "session_token_predicate"
                    or set(predicate.fields) != {"token"} or type(predicate.fields["token"]) is not str):
                raise AdmissionError("unknown session query predicate")

        def delete():
            def where(predicate):
                require_predicate(predicate)
                def run():
                    ids = [index for index, row in self.store.items() if row["token"] == predicate.fields["token"]]
                    for index in ids:
                        del self.store[index]
                    return []
                return DataRecord("session_delete_where", {"run": Capability("delete.run", run, True)})
            return DataRecord("session_delete", {"where": Capability("delete.where", where)})

        receiver = DataRecord("empty_receiver", {})
        model = DataRecord("sessions_model", {"objects": Capability("objects", objects),
                           "delete": Capability("delete", delete),
                           "token": DataRecord("session_token_column", {})})
        interpreter = SessionInterpreter(self.program, receiver,
                                        {"datetime": DataRecord("fixed_clock", {"now": Capability("clock.now", lambda: 0)})})
        if action == "lookup":
            result = interpreter.run("get_user_id", [model, token, increase_seconds])
        else:
            if increase_seconds is not None:
                raise ValueError("remove has no expiry-increase input")
            result = interpreter.run("remove_session", [model, token])
        after = self.snapshot()
        if action == "lookup" and len(selected) != 1:
            raise ValueError("interpreted selected-record observation count differs")
        return {"request": list(request), "token_argument": token,
                "increase_seconds": increase_seconds, "returned_user_id": result,
                "selected_record": selected[0] if selected else None,
                "decision": "allow" if action == "remove" or result is not None else "deny",
                "before_state": mask(before), "after_state": mask(after),
                "before_rows": serialized_rows(before), "after_rows": serialized_rows(after),
                "removed_ids": sorted(set(row["id"] for row in before) - set(row["id"] for row in after)),
                "store_changed": before != after}
