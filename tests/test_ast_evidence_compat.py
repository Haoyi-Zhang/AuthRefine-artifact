import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

import source_study
from source_study.independent_observer import source as observer_source
from source_study.stateful_sequence import source as session_source
import tempfile


# File-backed capture avoids a PIPE EOF wait when a verifier launches descendants
# that inherit stdout/stderr. It preserves subprocess.run's captured-output API
# while making the log descriptor independent of descendant lifetime.
_ORIGINAL_SUBPROCESS_RUN = subprocess.run

def _run_file_backed(*popenargs, **kwargs):
    capture_output = bool(kwargs.pop("capture_output", False))
    stdout_pipe = capture_output or kwargs.get("stdout") is subprocess.PIPE
    stderr_pipe = capture_output or kwargs.get("stderr") is subprocess.PIPE
    if not stdout_pipe and not stderr_pipe:
        return _ORIGINAL_SUBPROCESS_RUN(*popenargs, **kwargs)
    if capture_output and ("stdout" in kwargs or "stderr" in kwargs):
        raise ValueError("stdout and stderr arguments may not be used with capture_output")
    check = bool(kwargs.pop("check", False))
    text_mode = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
    encoding = kwargs.get("encoding") or "utf-8"
    errors = kwargs.get("errors") or "replace"
    out_file = tempfile.TemporaryFile(mode="w+b") if stdout_pipe else None
    err_file = tempfile.TemporaryFile(mode="w+b") if stderr_pipe else None
    try:
        if stdout_pipe:
            kwargs["stdout"] = out_file
        if stderr_pipe:
            kwargs["stderr"] = err_file
        result = _ORIGINAL_SUBPROCESS_RUN(*popenargs, check=False, **kwargs)
        if out_file is not None:
            out_file.flush(); out_file.seek(0)
            data = out_file.read()
            result.stdout = data.decode(encoding, errors) if text_mode else data
        if err_file is not None:
            err_file.flush(); err_file.seek(0)
            data = err_file.read()
            result.stderr = data.decode(encoding, errors) if text_mode else data
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, result.args,
                output=getattr(result, "stdout", None),
                stderr=getattr(result, "stderr", None),
            )
        return result
    finally:
        if out_file is not None: out_file.close()
        if err_file is not None: err_file.close()



ART = Path(__file__).resolve().parents[1]


class AstEvidenceCompatibilityTests(unittest.TestCase):
    def test_package_import_does_not_eagerly_import_evidence_targets(self):
        code = r'''
import json, sys
import source_study
names = [
    "source_study.stateful_sequence.source",
    "source_study.independent_observer.source",
]
before = {name: name in sys.modules for name in names}
from source_study.independent_observer import source
result = {
    "before": before,
    "after": {name: name in sys.modules for name in names},
    "patched": source.ast is not __import__("ast"),
    "metadata": source_study.ast_evidence_metadata(),
}
print(json.dumps(result, sort_keys=True))
'''
        completed = _run_file_backed(
            [sys.executable, "-B", "-c", code],
            cwd=ART,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["before"], {
            "source_study.independent_observer.source": False,
            "source_study.stateful_sequence.source": False,
        })
        self.assertTrue(result["after"]["source_study.independent_observer.source"])
        self.assertFalse(result["after"]["source_study.stateful_sequence.source"])
        self.assertTrue(result["patched"])
        self.assertFalse(result["metadata"]["eager_target_imports"])

    def test_evidence_dump_matches_empty_field_representation(self):
        node = ast.parse("def f(x):\n    return x\n").body[0]
        evidence = session_source.ast.dump(node, include_attributes=False)
        if sys.version_info >= (3, 13):
            explicit = ast.dump(node, include_attributes=False, show_empty=True)
            omitted = ast.dump(node, include_attributes=False, show_empty=False)
            self.assertEqual(evidence, explicit)
            self.assertNotEqual(evidence, omitted)
        self.assertIn("decorator_list=[]", evidence)

    def test_runtime_ast_default_is_not_changed_process_wide(self):
        node = ast.parse("def f(x):\n    return x\n").body[0]
        if sys.version_info >= (3, 13):
            self.assertEqual(ast.dump(node), ast.dump(node, show_empty=False))
            self.assertNotEqual(ast.dump(node), session_source.ast.dump(node))
        self.assertIsNot(ast, session_source.ast)
        self.assertIsNot(ast, observer_source.ast)

    def test_explicit_omission_remains_available_in_scoped_proxy(self):
        if sys.version_info < (3, 13):
            self.skipTest("show_empty was added in Python 3.13")
        node = ast.parse("def f(x):\n    return x\n").body[0]
        self.assertNotEqual(
            session_source.ast.dump(node),
            session_source.ast.dump(node, show_empty=False),
        )

    def test_session_manifest_matches_retained_acquisition(self):
        retained = json.loads(
            (ART / "results/session-initial-state/source-execution.json").read_text(encoding="utf-8")
        )[0]["manifest"]
        self.assertEqual(session_source.load()[3], retained)

    def test_source_observer_manifest_matches_retained_acquisition(self):
        from source_study.independent_observer.observer import baseline

        retained = json.loads(
            (ART / "results/source-observer/source-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline()["source_manifest"], retained)

    def test_source_observer_identity_gate_accepts_only_declared_compatibility_extra(self):
        from source_study import verify_source_observer as verifier

        base = {name: verifier.sha(ART / name) for name in verifier.PRODUCTION_SOURCES}
        acquisition = {path.name: verifier.sha(path) for path in verifier.OBSERVER.glob("*.py")}
        runtime = {"source_sha256": acquisition, "production_module_sha256": base}
        verifier.source_identities(runtime)

        compatible = {
            **base,
            **{name: verifier.sha(ART / name) for name in verifier.OPTIONAL_COMPATIBILITY_SOURCES},
        }
        runtime["production_module_sha256"] = compatible
        verifier.source_identities(runtime)

        for changed in ("unknown", "stale"):
            with self.subTest(changed=changed):
                altered = dict(compatible)
                if changed == "unknown":
                    altered["source_study/unknown.py"] = "0" * 64
                else:
                    altered[verifier.OPTIONAL_COMPATIBILITY_SOURCES[0]] = "0" * 64
                runtime["production_module_sha256"] = altered
                with self.assertRaisesRegex(ValueError, "complete production/shared-module identities"):
                    verifier.source_identities(runtime)

    def test_metadata_records_scope_representation_and_runtime(self):
        metadata = source_study.ast_evidence_metadata()
        self.assertEqual(metadata["representation"], "ast.dump-empty-fields-v1")
        self.assertEqual(metadata["python"], f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        self.assertTrue(metadata["show_empty_default"])
        self.assertTrue(metadata["runtime_ast_unchanged"])
        self.assertFalse(metadata["process_global_patch"])
        self.assertFalse(metadata["eager_target_imports"])
        self.assertEqual(metadata["patch_strategy"], "post-load-local-binding")
        self.assertEqual(len(metadata["scoped_modules"]), 2)


if __name__ == "__main__":
    unittest.main()
