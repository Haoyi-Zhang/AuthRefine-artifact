"""Fixed-source admission for two complete Piccolo session methods.

The native arm loads the complete original module with its real dependencies.
The effect arm retains the complete selected function bodies and removes only
their classmethod decorators and type annotations. Neither accepts arbitrary
source paths. The single control is an explicitly introduced in-memory edit.
"""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path

ART = Path(__file__).resolve().parents[2]
SOURCE = "source_study/source/h19/after/piccolo_api/session_auth/tables.py"
SHA256 = "b1e06075e16681ff1119e36f66d785f118baeb53bf74c485c508eafdf272e531"
COMMIT = "520ec2567ae1d2cc417c8c0d1ad0ddc05549a8a4"
METHODS = ("get_user_id", "remove_session")


def ast_hash(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def load(control=None):
    if control not in (None, "omit_delete"):
        raise ValueError("unknown session source control")
    path = ART / SOURCE
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("session source identity differs")
    tree = ast.parse(raw, filename=str(path))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SessionsBase"]
    if len(classes) != 1:
        raise ValueError("ambiguous session source class")
    selected = {}
    manifest = []
    for name in METHODS:
        found = [n for n in classes[0].body if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
        if len(found) != 1:
            raise ValueError("ambiguous selected session function")
        original = found[0]
        node = deepcopy(original)
        if control == "omit_delete" and name == "remove_session":
            if (len(node.body) != 2 or not isinstance(node.body[0], ast.Expr)
                    or not isinstance(node.body[0].value, ast.Constant)
                    or not isinstance(node.body[1], ast.Expr)
                    or not isinstance(node.body[1].value, ast.Await)):
                raise ValueError("omitted delete source site changed")
            node.body[1] = ast.copy_location(ast.Return(value=ast.Constant(None)), node.body[1])
            classes[0].body[classes[0].body.index(original)] = deepcopy(node)
        manifest.append({"function": "SessionsBase." + name,
                         "line": original.lineno, "end_line": original.end_lineno,
                         "original_ast_sha256": ast_hash(original),
                         "executed_ast_sha256": ast_hash(node),
                         "control": control if name == "remove_session" else None})
        # The effect interpreter receives cls explicitly. Decorator evaluation
        # and annotations are outside that selected-method call interface.
        node.decorator_list = []
        node.returns = None
        for arg in (*node.args.args, *node.args.posonlyargs, *node.args.kwonlyargs):
            arg.annotation = None
        node._effect_method = False
        node._effect_bound_self = False
        selected[name] = ast.fix_missing_locations(node)
    manifest = {"path": SOURCE, "sha256": SHA256, "commit": COMMIT,
                "url": "https://github.com/piccolo-orm/piccolo_api/blob/" + COMMIT + "/piccolo_api/session_auth/tables.py",
                "license": "source_study/source/h19/piccolo-api-LICENSE",
                "functions": manifest, "control": control,
                "native_module_imports_and_class_initialization": True,
                "effect_selected_bodies_complete": True,
                "clock": "fixed, naive datetime 2020-01-01T00:00:00",
                "source_files_modified": False}
    return raw, ast.fix_missing_locations(tree), selected, manifest
