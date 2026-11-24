"""Scoped compatibility for retained source-study AST evidence.

The retained AST manifests were acquired on Python 3.12. Python 3.13 added
``show_empty`` to ``ast.dump`` and changed the default text representation by
omitting empty fields. Two evidence-producing modules persist hashes of that
text. A narrow import hook replaces only those modules' local ``ast`` binding
after each module has loaded. It does not import either evidence module merely
because the :mod:`source_study` package was imported.

The process-wide :mod:`ast` module, unrelated project modules, retained
manifests, selected upstream source files, and scientific records are unchanged.
"""
from __future__ import annotations

import ast as _runtime_ast
import importlib.abc
import importlib.machinery
import inspect
import sys
import types
from typing import Any

AST_EVIDENCE_REPRESENTATION = "ast.dump-empty-fields-v1"
AST_EVIDENCE_RUNTIME = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
_TARGET_MODULES = (
    "source_study.stateful_sequence.source",
    "source_study.independent_observer.source",
)
_original_ast_dump = _runtime_ast.dump
_supports_show_empty = "show_empty" in inspect.signature(_original_ast_dump).parameters


class _EvidenceAst(types.ModuleType):
    """Delegate to ``ast`` while stabilizing only evidence-producing dumps."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_runtime_ast, name)

    def dump(
        self,
        node: _runtime_ast.AST,
        annotate_fields: bool = True,
        include_attributes: bool = False,
        *,
        indent: int | str | None = None,
        show_empty: bool = True,
    ) -> str:
        if _supports_show_empty:
            return _original_ast_dump(
                node,
                annotate_fields=annotate_fields,
                include_attributes=include_attributes,
                indent=indent,
                show_empty=show_empty,
            )
        if show_empty is not True:
            raise TypeError("show_empty is unavailable before Python 3.13")
        return _original_ast_dump(
            node,
            annotate_fields=annotate_fields,
            include_attributes=include_attributes,
            indent=indent,
        )


_evidence_ast = _EvidenceAst("source_study._evidence_ast")


class _EvidenceLoader(importlib.abc.Loader):
    """Patch a target module only after its ordinary loader has executed."""

    def __init__(self, wrapped: importlib.abc.Loader) -> None:
        self._wrapped = wrapped

    def create_module(self, spec):
        create = getattr(self._wrapped, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module) -> None:
        self._wrapped.exec_module(module)
        module.ast = _evidence_ast


class _EvidenceFinder(importlib.abc.MetaPathFinder):
    """Wrap only the two evidence modules without importing them eagerly."""

    _authrefine_ast_evidence_finder = True

    def find_spec(self, fullname, path, target=None):
        if fullname not in _TARGET_MODULES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _EvidenceLoader(spec.loader)
        return spec


# Re-importing or reloading this package must not stack finders. Existing target
# modules are patched in place; absent targets remain absent until requested.
sys.meta_path[:] = [
    finder for finder in sys.meta_path
    if not getattr(finder, "_authrefine_ast_evidence_finder", False)
]
sys.meta_path.insert(0, _EvidenceFinder())
for _module_name in _TARGET_MODULES:
    _module = sys.modules.get(_module_name)
    if _module is not None:
        _module.ast = _evidence_ast


def ast_evidence_metadata() -> dict[str, Any]:
    """Describe the representation used for newly computed AST evidence."""
    return {
        "representation": AST_EVIDENCE_REPRESENTATION,
        "python": AST_EVIDENCE_RUNTIME,
        "show_empty_default": True,
        "scoped_modules": list(_TARGET_MODULES),
        "runtime_ast_unchanged": _runtime_ast.dump is _original_ast_dump,
        "process_global_patch": False,
        "eager_target_imports": False,
        "patch_strategy": "post-load-local-binding",
    }
