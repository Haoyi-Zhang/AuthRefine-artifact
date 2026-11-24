"""Residual-store theory and rejection of damaged actual native histories."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from benchmarks import audit_session_initial_state as finite
from source_study.session_initial_state import oracle, provenance, validation
from source_study.session_initial_state.io import decode, read, read_lines


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
RESULTS = ART / "results/session-initial-state"


class IndependentInitialStateTheoryTests(unittest.TestCase):
    def test_inverse_binding_direction(self):
        # beta(row 1)=credential 2; a forward lookup would incorrectly select row 3.
        self.assertEqual(oracle.step([2, 3, 1], 1, {"action": "lookup", "row": 2}), ("allow", 1, 1))

    def test_reset_semantics_change_exact_search_result(self):
        for observation in ("projected", "row"):
            for reset in ("none", "initial"):
                self.assertIsNone(finite.search(3, 1, observation, reset)["requests"])
            complete = finite.search(3, 1, observation, "complete")
            self.assertEqual((complete["requests"], complete["resets"]),
                             (3 if observation == "projected" else 2, 1))

    def test_anchors_can_be_absent_without_changing_free_cost(self):
        # Rows 0 and 3 are anchored; free rows 1 and 2 have mixed presence.
        for anchored_presence in (0, 1, 8, 9):
            result = finite.expected(4, 9, anchored_presence | 2, "projected", "complete")
            self.assertEqual(result, {"requests": 1, "resets": 0})
        self.assertEqual(finite.expected(4, 15, 0, "row", "none"), {"requests": 0, "resets": 0})

    def test_partial_store_language_preserves_absent_permutations(self):
        identity = (0, 1, 2, 3)
        absent_swap = (0, 1, 3, 2)
        present_swap = (1, 0, 2, 3)
        self.assertTrue(finite.matches_full_language(4, 3, identity, "projected", True)[0])
        self.assertTrue(finite.matches_full_language(4, 3, absent_swap, "projected", True)[0])
        self.assertTrue(finite.matches_full_language(4, 3, present_swap, "projected", False)[0])
        self.assertFalse(finite.matches_full_language(4, 3, present_swap, "projected", True)[0])
        self.assertFalse(finite.matches_full_language(4, 3, present_swap, "row", False)[0])


class NativeInitialStateEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = read(RESULTS / "inputs.json.gz")
        cls.traces = {row["id"]: row for row in read_lines(RESULTS / "native-traces.jsonl.gz")}
        cls.cases = {row["id"]: row for row in cls.inputs["cases"]}

    def case_and_trace(self, name="n3-initial1-projected"):
        return deepcopy(self.cases[name]), deepcopy(self.traces[name])

    def test_retained_report_matches_complete_read_only_validation(self):
        self.assertEqual(validation.verify(RESULTS), read(RESULTS / "validation.json.gz"))

    def test_earlier_mismatch_persists_across_complete_restoration(self):
        case, trace = self.case_and_trace()
        # This binding disagrees on L3 before restoration but agrees on R2,L2 after it.
        self.assertEqual(oracle.compare_history(case, trace, [3, 2, 1])[0], 0)
        report = oracle.certify(case, trace)
        self.assertEqual(report["surviving_bindings"], [[1, 2, 3]])

    def test_changed_initial_physical_token_is_rejected(self):
        case, trace = self.case_and_trace()
        trace["initial_rows"][0]["token"] = "changed-token"
        with self.assertRaisesRegex(ValueError, "initial physical rows"):
            oracle.certify(case, trace)

    def test_changed_returned_row_is_rejected_even_under_projected_observation(self):
        case, trace = self.case_and_trace("n3-reset-initial-projected")
        trace["events"][0]["observation"]["selected_record"]["id"] = 2
        with self.assertRaisesRegex(ValueError, "physical rows/selected record"):
            oracle.certify(case, trace)

    def test_omitted_native_event_is_rejected(self):
        case, trace = self.case_and_trace()
        trace["events"].pop()
        with self.assertRaisesRegex(ValueError, "event count"):
            oracle.certify(case, trace)

    def test_restoration_to_incomplete_rows_is_rejected(self):
        case, trace = self.case_and_trace()
        event = next(row for row in trace["events"] if row["action"] == "restore_complete")
        event["after_rows"].pop()
        with self.assertRaisesRegex(ValueError, "reconstruction changed rows"):
            oracle.certify(case, trace)

    def test_reset_initial_must_not_create_initially_absent_rows(self):
        case, trace = self.case_and_trace("n3-reset-initial-projected")
        event = next(row for row in trace["events"] if row["action"] == "reset_initial")
        event["after_state"] = 7
        event["after_rows"] = oracle.rows(3, 7)
        with self.assertRaisesRegex(ValueError, "restoration semantics"):
            oracle.certify(case, trace)

    def test_boolean_state_does_not_equal_integer_state(self):
        case, trace = self.case_and_trace()
        trace["initial_state"] = True
        with self.assertRaisesRegex(ValueError, "initial physical rows"):
            oracle.certify(case, trace)

    def test_candidate_family_damage_is_rejected(self):
        inputs = deepcopy(self.inputs)
        inputs["candidate_families"]["3"][1] = inputs["candidate_families"]["3"][0]
        with self.assertRaisesRegex(ValueError, "fixed bijection family"):
            validation.validate_inputs(inputs)

    def test_caller_observation_and_key_types_are_strict(self):
        for change in ("observation", "caller", "boolean-row", "unknown-key"):
            with self.subTest(change=change):
                inputs = deepcopy(self.inputs)
                case = inputs["cases"][0]
                if change == "observation":
                    case["observation"] = "raw-token"
                elif change == "caller":
                    case["word"][0] = {"action": "reset_initial"}
                elif change == "boolean-row":
                    case["word"][-1]["row"] = True
                else:
                    case["word"][0]["unrecognized"] = 0
                with self.assertRaises(ValueError):
                    validation.validate_inputs(inputs)


class InitialStateEvidenceBoundaryTests(unittest.TestCase):
    def test_json_rejects_duplicate_and_nonfinite_values(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_acquisition_rejects_existing_directory_before_dependency_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "existing.txt"
            sentinel.write_text("retained input\n")
            result = _run_file_backed([sys.executable, "-B", "-W", "error",
                                     str(ART / "source_study/session_initial_state/run.py"),
                                     "acquire", "--output", directory], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output directory already exists", result.stderr)
            self.assertEqual(sentinel.read_text(), "retained input\n")
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["existing.txt"])

    def test_finite_audit_refuses_overwrite_before_search(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "retained.json"
            destination.write_text("retained input\n")
            result = _run_file_backed([sys.executable, "-B", "-W", "error",
                                     str(ART / "benchmarks/audit_session_initial_state.py"),
                                     "--output", str(destination)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(destination.read_text(), "retained input\n")


class InitialStateProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = read(RESULTS / "acquisition.json")
        cls.dependencies = read(RESULTS / "native-dependencies.json.gz")

    def test_acquisition_code_identity_is_required(self):
        receipt = deepcopy(self.receipt)
        receipt["provenance"]["code_before"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "executed sources"):
            provenance.verify(RESULTS, receipt)

    def test_evidence_content_identity_is_required(self):
        receipt = deepcopy(self.receipt)
        receipt["provenance"]["evidence_files"][0]["bytes"] += 1
        with self.assertRaisesRegex(ValueError, "evidence file identity"):
            provenance.verify(RESULTS, receipt)

    def test_dependency_recheck_flag_requires_boolean_true(self):
        receipt = deepcopy(self.receipt)
        receipt["provenance"]["native_dependencies_rechecked"] = 1
        with self.assertRaisesRegex(ValueError, "dependencies were not rechecked"):
            provenance.verify(RESULTS, receipt)

    def test_actual_dependency_version_must_match_lock(self):
        record = deepcopy(self.dependencies)
        package = next(row for row in record["all_distributions"] if row["name"].lower() == "piccolo")
        package["version"] = "unrecorded-runtime"
        with self.assertRaisesRegex(ValueError, "installed distribution differs from lock"):
            provenance.validate_dependency_record(record)

    def test_runtime_headers_must_describe_the_same_python(self):
        receipt = deepcopy(self.receipt)
        receipt["python"] = "inconsistent-runtime"
        with self.assertRaisesRegex(ValueError, "Python runtime"):
            provenance.verify(RESULTS, receipt)

    def test_utc_interval_is_ordered_and_explicit(self):
        with self.assertRaisesRegex(ValueError, "UTC instant"):
            provenance.verify_timestamps("2026-11-20T01:00:00.000000", self.receipt["finished_utc"])
        with self.assertRaisesRegex(ValueError, "finish precedes start"):
            provenance.verify_timestamps(self.receipt["finished_utc"], self.receipt["started_utc"])


if __name__ == "__main__":
    unittest.main()
