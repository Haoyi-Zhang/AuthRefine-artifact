"""Select reviewed, immutable function bodies without importing an application.

This is a fixed experiment, not a sandbox for user-supplied Python. Whole-module
hashes, an exact function list and an AST envelope are all checked before
compilation. Only annotations and decorators are removed; selected bodies retain
their Python control flow. Mutations are explicit, separately identified inputs.
"""
import ast
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

ART = Path(__file__).resolve().parents[2]
SOURCES = {
    "health_models": ("source_study/source/healthchecks/hc/accounts/models.py",
                      "bea6b643ba108892a0f0310bd7af41fc46a82c00d9f46fd23551e73c3b5a7839"),
    "health_decorators": ("source_study/source/healthchecks/hc/api/decorators.py",
                          "8c87db19c35849356cada2a1d60abeab966c39f158ed074ff503027dc78b4c92"),
    "health_views": ("source_study/source/healthchecks/hc/api/views.py",
                     "0b6c90b3d36ef48c4872b8d9964362571442f2ca8e63709c52698d33ad590e79"),
    "event_permission": ("source_study/source/pretix/src/pretix/api/auth/permission.py",
                         "fd6b76ca6a039a9bc4b60e3a916fb69764dc7de7b47b0f18485898ec65e62fb9"),
    "event_token": ("source_study/source/pretix/src/pretix/base/models/organizer.py",
                    "8e5a6e38022d37ecc6d411bc72251dd64ef9513aa78049bbc662cdf3ea6c5473"),
}
WGER_PACKET = ("adaptation_study/sources.json.gz", "cf82777493c00475643752db6ca0cccfd10cec15cd78e570ada7f6cc9f0233f3")
WGER_SOURCES = {
    "wger_permission": ("wger/manager/api/permissions.py", "345e9f4fc311a12dc8ca16389d9436b395f4a696547e78e62dc2fb7af6c09f59"),
    "wger_view": ("wger/manager/api/views.py", "f762d3458fe7f040fa802bc9853ce20002bbdbbe9c218ec1f263b972e2946734"),
}
SELECTIONS = {
    "manager": ("health_models", "ProjectManager", "for_api_key"),
    "compare_key": ("health_models", "Project", "compare_api_key"),
    "error": ("health_decorators", None, "error"),
    "version": ("health_decorators", None, "_get_api_version"),
    "authorize": ("health_decorators", None, "authorize"),
    "authorize_read": ("health_decorators", None, "authorize_read"),
    "get_check": ("health_views", None, "get_check"),
    "resume": ("health_views", None, "resume"),
    "event_permission": ("event_permission", "EventPermission", "has_permission"),
    "event_access": ("event_token", "TeamAPIToken", "has_event_permission"),
    "event_grants": ("event_token", "TeamAPIToken", "get_event_permission_set"),
    "wger_permission": ("wger_permission", "RoutinePermission", "has_permission"),
    "wger_create": ("wger_view", "RoutineViewSet", "perform_create"),
}
MUTATIONS = {
    "read_wrong_version": "get_check",
    "read_foreign_serializer": "get_check",
    "resume_omit_save": "resume",
    "resume_repeat_flip": "resume",
    "resume_stale_ping": "resume",
    "pretix_wrong_organizer": "event_permission",
    "pretix_omit_grants": "event_permission",
    "wger_client_owner": "wger_create",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ast_sha(node):
    return sha(ast.dump(node, include_attributes=False).encode())


def checked(raw, expected, label):
    if sha(raw) != expected:
        raise ValueError("source identity differs: " + label)
    return raw.decode("utf-8")


def load_sources():
    raw = {key: checked((ART / path).read_bytes(), digest, path)
           for key, (path, digest) in SOURCES.items()}
    path, digest = WGER_PACKET
    compressed = (ART / path).read_bytes()
    if sha(compressed) != digest:
        raise ValueError("source packet identity differs")
    packet = json.loads(gzip.decompress(compressed))
    cases = [r for r in packet["rows"] if r["repository_id"] == 7705569]
    if len(cases) != 1 or cases[0]["snapshot"] != "a841e51c413843dfd16d8e51c6a3db2a119b84f5":
        raise ValueError("Wger source selection differs")
    for key, (path, digest) in WGER_SOURCES.items():
        matches = [m for m in cases[0]["modules"] if m["path"] == path]
        if len(matches) != 1:
            raise ValueError("ambiguous Wger module")
        raw[key] = checked(matches[0]["text"].encode(), digest, path)
    return raw


def select(text, owner, name):
    nodes = ast.parse(text).body
    if owner is not None:
        owners = [n for n in nodes if isinstance(n, ast.ClassDef) and n.name == owner]
        if len(owners) != 1:
            raise ValueError("ambiguous selected class")
        nodes = owners[0].body
    matches = [n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise ValueError("ambiguous selected function")
    return deepcopy(matches[0])


class SignatureOnly(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        node.decorator_list = []
        node.returns = None
        node.type_comment = None
        for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            a.annotation = None
        if node.args.vararg:
            node.args.vararg.annotation = None
        if node.args.kwarg:
            node.args.kwarg.annotation = None
        return self.generic_visit(node)


def envelope(node):
    forbidden = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef, ast.Await,
                 ast.With, ast.AsyncWith, ast.While, ast.Delete, ast.Global, ast.Nonlocal,
                 ast.Lambda, ast.Yield, ast.YieldFrom)
    for child in ast.walk(node):
        if isinstance(child, forbidden):
            raise ValueError("outside reviewed function envelope: " + type(child).__name__)
        if isinstance(child, ast.Name) and child.id.startswith("__"):
            raise ValueError("dunder name outside reviewed envelope")
        if isinstance(child, ast.Attribute) and child.attr.startswith("__"):
            raise ValueError("dunder attribute outside reviewed envelope")
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in {
                "eval", "exec", "compile", "open", "globals", "locals", "vars", "input"}:
            raise ValueError("unreviewed call")


def mutation(node, name):
    changed = 0
    if name == "read_wrong_version":
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "to_dict":
                for kw in call.keywords:
                    if kw.arg == "v":
                        kw.value = ast.Constant(value=1)
                        changed += 1
    elif name == "read_foreign_serializer":
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "to_dict":
                # A distinct existing Check is used after the original identity check.
                call.func.value = ast.Call(func=ast.Name(id="get_object_or_404", ctx=ast.Load()),
                                          args=[ast.Name(id="Check", ctx=ast.Load())],
                                          keywords=[ast.keyword(arg="code", value=ast.Constant(value="00000000-0000-0000-0000-000000000002"))])
                changed += 1
    elif name in ("resume_omit_save", "resume_repeat_flip"):
        body = []
        for stmt in node.body:
            call = stmt.value if isinstance(stmt, ast.Expr) else None
            method = call.func.attr if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) else None
            if name == "resume_omit_save" and method == "save":
                changed += 1
                continue
            body.append(stmt)
            if name == "resume_repeat_flip" and method == "create_flip":
                body.append(deepcopy(stmt))
                changed += 1
        node.body = body
    elif name == "resume_stale_ping":
        body = []
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and
                    isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == "last_ping"):
                changed += 1
                continue
            body.append(stmt)
        node.body = body
    elif name in ("pretix_wrong_organizer", "pretix_omit_grants"):
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Attribute):
                if name == "pretix_wrong_organizer" and stmt.targets[0].attr == "organizer":
                    stmt.value = ast.Name(id="owned_other_organizer", ctx=ast.Load())
                    changed += 1
                elif name == "pretix_omit_grants" and stmt.targets[0].attr == "eventpermset" and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "EventPermissionSet":
                    stmt.value = ast.Call(func=ast.Name(id="set", ctx=ast.Load()), args=[], keywords=[])
                    changed += 1
    elif name == "wger_client_owner":
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "save":
                for kw in call.keywords:
                    if kw.arg == "user":
                        kw.value = ast.Attribute(value=ast.Name(id="serializer", ctx=ast.Load()), attr="client_user", ctx=ast.Load())
                        changed += 1
    else:
        raise ValueError("unknown source mutation")
    if changed != 1:
        raise ValueError(f"mutation must select exactly one source site: {name} ({changed})")
    return ast.fix_missing_locations(node)


def nodes_and_manifest(control=None):
    if control is not None and control not in MUTATIONS:
        raise ValueError("unknown control")
    raw = load_sources()
    nodes, selections = {}, []
    for key, (module, owner, name) in SELECTIONS.items():
        original = select(raw[module], owner, name)
        selected = SignatureOnly().visit(deepcopy(original))
        before = ast_sha(selected)
        if MUTATIONS.get(control) == key:
            selected = mutation(selected, control)
        envelope(selected)
        after = ast_sha(selected)
        if MUTATIONS.get(control) == key and before == after:
            raise ValueError("control did not change executable AST")
        nodes[key] = selected
        selections.append({"key": key, "module": module, "owner": owner, "function": name,
                           "line": original.lineno, "end_line": original.end_lineno,
                           "original_ast_sha256": ast_sha(original),
                           "compiled_ast_sha256": after, "baseline_compiled_ast_sha256": before,
                           "mutation": control if MUTATIONS.get(control) == key else None})
    return nodes, {"source_files": {k: {"path": p, "sha256": h} for k, (p, h) in SOURCES.items()},
                   "wger_source_packet": {"path": WGER_PACKET[0], "sha256": WGER_PACKET[1]},
                   "wger_modules": {k: {"path": p, "utf8_sha256": h} for k, (p, h) in WGER_SOURCES.items()},
                   "functions": selections,
                   "transformations": ["remove function decorators, including functools.wraps",
                                       "remove function annotations without evaluating them"],
                   "module_imports_or_class_initializers_executed": False,
                   "original_function_bodies_compiled": True, "control": control}


def compile_functions(nodes, globals):
    result = {}
    # Separate namespaces prevent the two unrelated has_permission methods from
    # replacing one another. All globals come from the explicit finite harness.
    for key, node in nodes.items():
        scope = dict(globals)
        scope["__builtins__"] = {"len": len, "str": str, "dict": dict, "isinstance": isinstance,
                                 "hasattr": hasattr, "getattr": getattr, "any": any,
                                 "list": list, "tuple": tuple, "set": set, "ValueError": ValueError}
        module = ast.fix_missing_locations(ast.Module(body=[deepcopy(node)], type_ignores=[]))
        exec(compile(module, "<hash-bound-owned-observer>", "exec", dont_inherit=True), scope)
        result[key] = scope[node.name]
    return result
