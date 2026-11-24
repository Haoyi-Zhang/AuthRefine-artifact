"""Pinned original-source and native dependency gates, independent of the IR."""
from __future__ import annotations
import hashlib
import ast
import importlib.metadata
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parents[1]
SOURCE = HERE.parent / "source" / "h19"
PARTS = {"table": "piccolo_api/session_auth/tables.py", "crud": "piccolo_api/crud/endpoints.py"}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_pins(orm_version="1.16.0") -> dict:
    names = {"1.16.0": "pins.json", "1.34.0": "pins-1.34.json"}
    if orm_version not in names:
        raise ValueError("Only the two pinned ORM versions are admitted")
    return json.loads((HERE / names[orm_version]).read_text(encoding="utf-8"))


def registry_model(orm_version):
    pins = load_pins(orm_version)
    path = (SOURCE / "orm-contract/piccolo/table.py" if orm_version == "1.16.0" else
            HERE / "dependencies/piccolo-1.34.0/piccolo/table.py")
    raw = path.read_bytes()
    expected = next(r for r in pins["native_files"] if r["path"] == "piccolo/table.py")
    if digest(raw) != expected["sha256"]:
        raise ValueError("Packaged registry source differs from pinned native package")
    tree = ast.parse(raw)
    append = ast.dump(ast.parse("secret_columns.append(column)", mode="eval").body)
    choices = [node for node in ast.walk(tree) if isinstance(node, ast.If) and
               any(isinstance(item, ast.Expr) and ast.dump(item.value) == append for item in node.body)]
    if len(choices) != 1:
        raise ValueError("Registry insertion predicate is not uniquely bound")
    selected = choices[0]
    modes = {ast.dump(ast.parse("isinstance(column, Secret)", mode="eval").body): "secret-subclass",
             ast.dump(ast.parse("column._meta.secret", mode="eval").body): "secrecy-metadata"}
    mode = modes.get(ast.dump(selected.test))
    if mode is None:
        raise ValueError("Native registry predicate lies outside the independent comparison")
    return {"orm_version": orm_version, "path": "piccolo/table.py", "sha256": digest(raw),
            "line": selected.lineno, "predicate": ast.unparse(selected.test), "predicate_mode": mode}


def check_source(root: Path = SOURCE) -> dict:
    pins = load_pins()
    rows = []
    for row in pins["original_files"]:
        raw = (root / row["path"]).read_bytes()
        if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
            raise ValueError(f"Pinned H19 source changed: {row['path']}")
        rows.append(dict(row))
    return {"files": rows, "producer_before_commit": pins["producer_before_commit"],
            "producer_after_commit": pins["producer_after_commit"]}


def check_native(orm_version="1.16.0") -> dict:
    pins = load_pins(orm_version)
    versions = {}
    for name, expected in pins["required_versions"].items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError(f"Native dependency differs: {name}: {actual} != {expected}")
        versions[name] = actual
    checked = []
    for row in pins["native_files"]:
        path = importlib.metadata.distribution(row["distribution"]).locate_file(row["path"])
        raw = path.read_bytes()
        if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
            raise ValueError(f"Native dependency source changed: {row['path']}")
        checked.append(dict(row))
    return {"versions": versions, "native_files": checked,
            "python": sys.version, "all_distributions": sorted(
                [{"name": d.metadata["Name"], "version": d.version}
                 for d in importlib.metadata.distributions()], key=lambda x: x["name"].lower())}


def load_original(label: str, part: str, suffix: str):
    if label not in ("before", "after") or part not in PARTS:
        raise ValueError("Only the two pinned H19 source versions are admitted")
    check_source()
    path = SOURCE / label / PARTS[part]
    package = "piccolo_api.crud" if part == "crud" else "piccolo_api.session_auth"
    name = f"{package}._authrefine_h19_{label}_{suffix}"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = package
    sys.modules[name] = module
    try:
        exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module
